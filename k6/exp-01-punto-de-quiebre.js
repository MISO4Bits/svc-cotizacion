// EXP-01 — Punto de quiebre de bff-web + svc-cotizacion (una sola réplica
// de cada uno, sin HPA) a través de la plataforma real (API Gateway ->
// bff-web -> svc-cotizacion), no contra svc-cotizacion directo.
//
// Un solo usuario/token para todo el ramp (evita crear miles de clientes):
// setup() registra la cuenta una vez, otorga consentimiento OPEN_FINANCE
// (dispara el cálculo async del perfil en Perfilamiento) y hace una
// cotización de calentamiento para que el perfil ya esté en caché (Redis)
// antes de que arranque la medición real — de lo contrario solo la primera
// iteración pagaría el cache-miss, un ruido despreciable a esta escala pero
// evitable.
//
// El objetivo es el escenario "Cotización embebida" del enunciado: p95 <=
// 250ms, p99 <= 500ms extremo a extremo. Cada etapa tiene SU PROPIO
// threshold, etiquetado con `etapa:<tasa>` — nunca uno solo acumulado
// sobre toda la corrida. Motivo (encontrado en vivo, 2026-09-19): un
// threshold sobre un Trend evalúa TODAS las muestras desde el inicio del
// test; con miles de muestras rápidas de las primeras etapas ya
// acumuladas, las muestras lentas de una etapa mala quedan diluidas y el
// p95 acumulado nunca cruza 250ms aunque el p95 reciente sí — el test
// nunca se corta solo. Con un threshold por etapa, cada uno solo ve las
// muestras de SU propia etapa.
//
// requiere BFF_SESSION_TTL_SECONDS ya ampliado en dev (el token de 1h por
// defecto no alcanza para un ramp largo) y que Cloud Armor (WAF, límite de
// 100 req/min por IP) NO esté aplicado — si se reaplica el WAF sobre este
// ambiente hay que revisar ese límite antes de volver a correr esto.
//
// Local, desde tu red (mide latencia real de cliente, incluida la distancia
// a southamerica-east1):
//   k6 run k6/exp-01-punto-de-quiebre.js
//
// Desde k6 Cloud (Grafana) — el que aísla el punto de quiebre por carga del
// resto de la latencia de red, corriendo desde su propia infraestructura:
//   k6 cloud login
//   k6 cloud run k6/exp-01-punto-de-quiebre.js
//
// Config por env: -e BASE_URL=... -e RATES="1000,3000,5000,7500"
//                 -e RAMP_DURATION=30s -e HOLD_DURATION=60s -e MAX_VUS=100

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "https://dev.solventa4bits.com/web";
const RAMP_DURATION = __ENV.RAMP_DURATION || "30s";
const HOLD_DURATION = __ENV.HOLD_DURATION || "60s";
// Tope real: el plan de k6 Cloud de esta cuenta permite máximo 100 VUs por
// test (2026-09-19) — si algún día se sube el plan, subir esto también. Si
// el servidor aguanta con latencia baja, 100 VUs alcanzan para tasas altas
// (Little's Law); si no, el que se agota primero son los VUs, no
// necesariamente el servidor — mirar la métrica `dropped_iterations` para
// distinguir un caso del otro.
const PRE_ALLOCATED_VUS = Number(__ENV.PRE_ALLOCATED_VUS || 20);
const MAX_VUS = Number(__ENV.MAX_VUS || 100);

// Cotizaciones/min a probar. La primera corrida de EXP-01 (2026-09-19, 1
// réplica de bff-web y de svc-cotizacion) pasó limpio hasta 5.000/min y se
// rompió al entrar a 7.500/min, así que las etapas bajas ya no aportan: se
// deja una sola de referencia y se afina de a 1.000 entre 3.000 y 8.000
// para acotar el techo con más precisión; hacia arriba se espacia hasta el
// techo del enunciado (50.000/min).
const RATES_POR_MIN = (__ENV.RATES || "1000,3000,4000,5000,6000,7000,8000,10000,15000,20000,30000,50000")
  .split(",")
  .map(Number);

const iterPorSeg = (porMinuto) => Math.max(1, Math.round(porMinuto / 60));

// "30s" / "1m" / "1m30s" -> milisegundos, para calcular en qué ventana de
// tiempo transcurrido cae cada etapa (no hay forma nativa en k6 de
// preguntarle al executor "qué etapa está activa ahora mismo" desde
// dentro de una VU).
function duracionMs(texto) {
  const m = /^(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?$/.exec(texto.trim());
  if (!m) throw new Error(`duración no reconocida: ${texto}`);
  const minutos = Number(m[1] || 0);
  const segundos = Number(m[2] || 0);
  return (minutos * 60 + segundos) * 1000;
}

const RAMP_MS = duracionMs(RAMP_DURATION);
const HOLD_MS = duracionMs(HOLD_DURATION);

const stages = [];
// [{ rate, startMs, endMs }] — startMs/endMs son offsets desde el arranque
// del escenario, usados en runtime para decidir la etiqueta `etapa` de
// cada request.
const ventanasPorEtapa = [];
{
  let offset = 0;
  for (const rate of RATES_POR_MIN) {
    stages.push({ target: iterPorSeg(rate), duration: RAMP_DURATION });
    offset += RAMP_MS;
    stages.push({ target: iterPorSeg(rate), duration: HOLD_DURATION });
    const endMs = offset + HOLD_MS;
    ventanasPorEtapa.push({ rate, startMs: offset, endMs });
    offset = endMs;
  }
}

function etapaEnCurso(elapsedMs) {
  for (const v of ventanasPorEtapa) {
    if (elapsedMs < v.endMs) return v.rate;
  }
  return RATES_POR_MIN[RATES_POR_MIN.length - 1];
}

const latencia_e2e = new Trend("cotizacion_latencia_e2e", true);

const thresholds = {
  // Red de seguridad global (no por etapa): si el % de error total se
  // dispara, algo se rompió de verdad, sin importar en qué etapa.
  http_req_failed: [{ threshold: "rate<0.05", abortOnFail: true, delayAbortEval: "15s" }],
};
for (const rate of RATES_POR_MIN) {
  thresholds[`cotizacion_latencia_e2e{etapa:${rate}}`] = [
    { threshold: "p(95)<250", abortOnFail: true, delayAbortEval: "15s" },
  ];
}

export const options = {
  // Solo aplica a `k6 cloud run` (ignorado en `k6 run` local) — 100% de la
  // carga sale desde São Paulo en vez de repartirse entre zonas por
  // defecto, para aislar el punto de quiebre por carga de la latencia de
  // distancia (confirmado 2026-09-19: la corrida local desde Bogotá se
  // corta de inmediato por el piso de red, no por capacidad del servidor).
  cloud: {
    distribution: {
      saoPaulo: { loadZone: "amazon:br:sao paulo", percent: 100 },
    },
  },
  scenarios: {
    ramp_hasta_quiebre: {
      executor: "ramping-arrival-rate",
      startRate: iterPorSeg(RATES_POR_MIN[0]),
      timeUnit: "1s",
      preAllocatedVUs: PRE_ALLOCATED_VUS,
      maxVUs: MAX_VUS,
      stages,
    },
  },
  thresholds,
};

const CUERPO_COTIZACION = JSON.stringify({
  datosCredito: {
    valorCredito: 150000000,
    plazoMeses: 240,
    edad: 38,
    entidadAcreedora: "Banco X",
    saldoInsoluto: 140000000,
  },
  cuestionarioHabitos: {
    consumeTabaco: false,
    actividadFisica: "REGULAR",
    condicionesPreexistentes: false,
    dependientesEconomicos: 2,
  },
});

export function setup() {
  const ts = Date.now();
  const registro = http.post(
    `${BASE_URL}/v1/registro`,
    JSON.stringify({
      email: `k6-exp01-${ts}@example.com`,
      password: "ClaveSegura2026!",
      tipoDocumento: "CC",
      numeroDocumento: `${ts}`,
      primerNombre: "K6",
      primerApellido: "ExpUno",
      fechaNacimiento: "1990-01-01",
      politicaVersion: "v1",
      aceptaTerminos: true,
    }),
    { headers: { "Content-Type": "application/json" } }
  );
  if (!check(registro, { "registro 201": (r) => r.status === 201 })) {
    throw new Error(`setup: registro falló (${registro.status}): ${registro.body}`);
  }
  const { sesion, cuenta } = registro.json();
  const authHeaders = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${sesion.accessToken}`,
  };

  const consentimiento = http.post(
    `${BASE_URL}/v1/cuenta/consentimientos`,
    JSON.stringify({ scope: "OPEN_FINANCE", politicaVersion: "v1" }),
    { headers: authHeaders }
  );
  if (!check(consentimiento, { "consentimiento 201": (r) => r.status === 201 })) {
    throw new Error(`setup: consentimiento falló (${consentimiento.status}): ${consentimiento.body}`);
  }

  // Le da tiempo a Perfilamiento de consumir el evento y calcular el perfil
  // antes del calentamiento de caché de abajo.
  sleep(5);

  // Cache-warm: paga el único cache-miss fuera de la ventana medida.
  http.post(`${BASE_URL}/v1/cotizaciones`, CUERPO_COTIZACION, { headers: authHeaders });

  console.log(`setup listo — cliente_id=${cuenta.clienteId}`);
  // testStartTime se captura acá, no en la primera iteración del default(),
  // para que coincida con el arranque real del escenario (el executor
  // empieza a contar sus stages desde que termina setup()).
  return { accessToken: sesion.accessToken, testStartTime: Date.now() };
}

export default function (data) {
  const etapa = String(etapaEnCurso(Date.now() - data.testStartTime));
  const res = http.post(`${BASE_URL}/v1/cotizaciones`, CUERPO_COTIZACION, {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${data.accessToken}`,
    },
    tags: { etapa },
  });
  latencia_e2e.add(res.timings.duration, { etapa });
  check(res, { "status 201": (r) => r.status === 201 });
}
