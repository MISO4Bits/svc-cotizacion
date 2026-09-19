// EXP-02 — Resiliencia ante degradación de proveedores externos, corriendo
// DENTRO del clúster (Job de k6, ver exp-02-job.yaml): sin la red de Bogotá
// ni el gateway de por medio, la latencia medida es la del servicio.
//
// Dos modos (MODO):
//   perfil     POST /perfiles en svc-perfilamiento. El escenario se elige por
//              número de documento; WireMock (deploy/apps/wiremock) responde
//              distinto según el documento, así no hay que reiniciar nada
//              entre escenarios. Objetivo BITS-80: p95 <= 400 ms, p99 <= 800 ms.
//   cotizacion POST /cotizaciones en svc-cotizacion, cliente nuevo cada
//              iteración (cache miss => llama a Perfilamiento). Sirve para el
//              escenario "Perfilamiento caído" (escalarlo a 0 réplicas).
//              Objetivo BITS-79 (por confirmar): p95 <= 250 ms, p99 <= 500 ms.
//
// ESCENARIO (solo modo perfil) -> documento que dispara el mock:
//   normal      1234567890  ambos proveedores sanos
//   timeout     9999999999  ambos responden a los 5 s (dispara el timeout)
//   error503    8888888888  ambos responden 503 de inmediato
//   solo-of     7777777777  solo Open Finance cae (degradación parcial)
//
// Config por env: -e MODO=perfil -e ESCENARIO=timeout -e RATE=30 -e DURACION=3m
//                 -e PERFIL_URL=... -e COTIZACION_URL=... -e P95_MS=400 -e P99_MS=800

import http from "k6/http";
import { check } from "k6";
import { Counter, Trend } from "k6/metrics";

const MODO = __ENV.MODO || "perfil";
const ESCENARIO = __ENV.ESCENARIO || "normal";
const RATE = Number(__ENV.RATE || 30);
const DURACION = __ENV.DURACION || "3m";
const PERFIL_URL = __ENV.PERFIL_URL || "http://svc-perfilamiento.svc-perfilamiento.svc.cluster.local";
const COTIZACION_URL = __ENV.COTIZACION_URL || "http://svc-cotizacion.svc-cotizacion.svc.cluster.local";

const DOCUMENTOS = {
  normal: "1234567890",
  timeout: "9999999999",
  error503: "8888888888",
  "solo-of": "7777777777",
};
if (MODO === "perfil" && !DOCUMENTOS[ESCENARIO]) {
  throw new Error(`ESCENARIO desconocido: ${ESCENARIO} (${Object.keys(DOCUMENTOS).join(", ")})`);
}

const P95 = Number(__ENV.P95_MS || (MODO === "perfil" ? 400 : 250));
const P99 = Number(__ENV.P99_MS || (MODO === "perfil" ? 800 : 500));

const latencia = new Trend("exp02_latencia", true);
const degradadas = new Counter("exp02_degradadas");
const completas = new Counter("exp02_completas");

export const options = {
  scenarios: {
    carga_constante: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: DURACION,
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  tags: { modo: MODO, escenario: ESCENARIO },
  thresholds: {
    exp02_latencia: [`p(95)<${P95}`, `p(99)<${P99}`],
    // el servicio nunca debe romperse: la falla del proveedor se degrada, no se propaga
    http_req_failed: ["rate<0.02"],
  },
};

const COTIZACION_CUERPO = JSON.stringify({
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

export default function () {
  const cliente = `exp02-${__VU}-${__ITER}-${Date.now()}`;
  let res;
  if (MODO === "perfil") {
    res = http.post(
      `${PERFIL_URL}/perfiles`,
      JSON.stringify({ clienteId: cliente, numeroDocumento: DOCUMENTOS[ESCENARIO] }),
      { headers: { "Content-Type": "application/json" } },
    );
  } else {
    res = http.post(`${COTIZACION_URL}/cotizaciones`, COTIZACION_CUERPO, {
      headers: { "Content-Type": "application/json", "X-Cliente-Id": cliente },
    });
  }

  latencia.add(res.timings.duration);
  if (!check(res, { "status 201": (r) => r.status === 201 })) return;

  let degradada;
  if (MODO === "perfil") {
    degradada = (res.json("fuentesNoDisponibles") || []).length > 0;
  } else {
    degradada = res.json("oferta.personalizado") === false;
  }
  (degradada ? degradadas : completas).add(1);
}
