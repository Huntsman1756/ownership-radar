# Methodology — G0 Acquisition Probe

## Principles applied

- CNMV is the primary source; everything is captured as raw bytes with
  `sha256`, URL, headers and `retrieved_at` **before** normalization.
- No fuzzy matching, no inferred identity, no LLM anywhere in the pipeline.
- `notice_key = (source_family, source_registration_number)`. A content-hash
  fallback (`identity_status = PROVISIONAL_CONTENT_HASH`) exists in code but
  was **never needed**: 100% of observed notices carry an official
  "Número de registro (de entrada)".
- `notice_observation` is append-only (INSERT-only in code); the canonical
  `notice` projection may be UPSERTed; `run_seen` records set membership
  per run. Disappearances are recorded as observations with
  `present_in_source = 0` and `status_observed = SOURCE_DISAPPEARANCE_OBSERVED`
  — never auto-promoted to a stronger verdict.
- Three clocks kept separate: `event_date` (inside the document, only at
  listing granularity here), `filing_date` (F.Registro Entrada CNMV),
  `observed_at` (per observation, tied to `run_id`).

## What was enumerated, per issuer (SAN=A39000013, BBVA=A48265169)

| family      | surface                                               | mechanism                          |
|-------------|-------------------------------------------------------|------------------------------------|
| `nod`       | `/portal/consultas/directivos-resultado?nif=`         | global paginated list, `page=N`, supports `fechad`/`fechah` windowing |
| `nod_legacy`| `/portal/consultas/derechosvoto/notificacionesanterioresdirectivos?nif=` | per-person grid -> `otrasnotificacionesdirectivos.aspx?qS={ephemeral}` history |
| `ps`        | `/portal/consultas/derechosvoto/ps_ac_ini.aspx?nif=`  | hub -> current-holders grid -> per-holder `NotificacionesAnteriores.aspx?qS={ephemeral}` history; plus `personasotrasnotificaciones` (ex-holders/pre-2020-03-02 consejeros) |
| `ac`        | same hub                                              | `Autocartera` section -> `NotificacionesAnterioresAC` history |
| annulments  | `NotificacionesAnuladas.aspx?qS={ephemeral}`          | linked from history rows; states "registro de entrada X anula ..." |
| issuer id   | `/portal/consultas/ee/datosgenerales.aspx?nif=`       | NIF + LEI + capital                |
| incorporations | `/portal/Consultas/BusquedaUltimosDias`            | last-5-days, issuer-level counts per registry (no reg numbers) |

## Evidence classes used in results.md / gates.md

- `PROVEN` — directly demonstrated by captured raw evidence or explicit
  source text.
- `OBSERVED` — seen in our corpus, consistent, but not independently
  re-verified.
- `DERIVED` — computed by the probe from evidence (e.g. regime from
  filing_date + template fingerprint).
- `UNKNOWN` — stated openly.
