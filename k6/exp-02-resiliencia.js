// EXP-02 — Resiliencia de la cotización ante degradación de Perfilamiento.
//
//   k6 run k6/exp-02-resiliencia.js
//   k6 run -e URL_BASE=http://localhost:8080 -e RATE=30 -e DURACION=3m k6/exp-02-resiliencia.js
//
// Cambiá el escenario de WireMock ANTES de cada corrida (ver mock-perfilamiento/README.md
// y la tabla de k6/README.md).

import http from "k6/http";
import { check } from "k6";
import { Counter, Trend } from "k6/metrics";

const URL_BASE = __ENV.URL_BASE || "http://localhost:8080";
const RATE = Number(__ENV.RATE || 30);
const DURACION = __ENV.DURACION || "3m";

const latencia_e2e = new Trend("cotizacion_latencia_e2e", true);
const degradadas = new Counter("cotizacion_degradadas");
const personalizadas = new Counter("cotizacion_personalizadas");

export const options = {
  scenarios: {
    carga_constante: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: DURACION,
      preAllocatedVUs: 100,
      maxVUs: 400,
    },
  },
  thresholds: {
    // objetivo BITS-80: p95 <= 400 ms, p99 <= 800 ms E2E
    cotizacion_latencia_e2e: ["p(95)<400", "p(99)<800"],
    // el servicio nunca debería romperse: casi 0 respuestas no-201
    http_req_failed: ["rate<0.02"],
  },
};

const CUERPO = JSON.stringify({
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
  const res = http.post(`${URL_BASE}/cotizaciones`, CUERPO, {
    headers: {
      "Content-Type": "application/json",
      "X-Cliente-Id": `cli-${__VU}-${__ITER}`,
    },
  });

  latencia_e2e.add(res.timings.duration);

  const ok = check(res, { "status 201": (r) => r.status === 201 });
  if (!ok) return;

  const oferta = res.json("oferta");
  if (oferta && oferta.personalizado === false) {
    degradadas.add(1);
  } else {
    personalizadas.add(1);
  }
}
