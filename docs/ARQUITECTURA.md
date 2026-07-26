# Arquitectura del buscador CARIBDIS

## Estado inicial del repositorio

El proyecto de partida contiene:

- `scraper_boe_boja_social.py`: scraper monolítico sin dependencias externas. Descarga el índice diario del BOE y el feed Atom del BOJA, recupera el detalle de cada anuncio, aplica un filtro social y añade resultados a un TXT acumulativo.
- `informes_boe_boja_social/resultados_ayudas_sociales_boe_boja.txt`: histórico legible del scraper original.
- `.github/workflows/revisar-boe-boja-social.yml`: ejecución diaria y manual, con commit automático del TXT cuando cambia.

La implementación original ya dispone de reintentos, timeout, captura de errores por fuente y deduplicación por URL dentro de cada ejecución. Sus límites principales son:

- BOE y BOJA están acoplados al filtrado, scoring y renderizado.
- El modelo de datos no representa presupuesto, cofinanciación, estado, tipo de beneficiario, consorcio o riesgos.
- No existe histórico estructurado para comparar cambios.
- El único informe es acumulativo y no separa oportunidades abiertas, recurrentes o descartadas.
- El workflow solo permite una fecha final y un número de días.

## Objetivos de diseño

1. Mantener ejecutable el scraper BOE/BOJA y su TXT actual.
2. Separar adquisición, normalización, scoring, histórico y presentación.
3. Permitir añadir fuentes y municipios mediante JSON, sin editar el código.
4. Tolerar el fallo de una fuente y reflejarlo en el informe.
5. No inferir como oficiales fechas, importes o requisitos no publicados.
6. Limitar las consultas a páginas oficiales o verificables configuradas.
7. Generar un único informe principal, reemplazado en cada ejecución, y conservar el histórico en JSON interno.

## Componentes

```text
buscador_caribdis.py
caribdis_search/
  cli.py                 argumentos y periodo de revisión
  config.py              carga y validación de archivos JSON
  models.py              oportunidad, incidencia y resultado de ejecución
  scoring.py             scoring CARIBDIS por bloques (0-100)
  extractors.py          fechas, importes, porcentajes y requisitos
  history.py             deduplicación, cambios y recurrencia
  report.py              informe único y ranking
  runner.py              coordinación tolerante a fallos
  sources/
    base.py              contrato común de fuente
    boe_boja.py          adaptador del scraper heredado
    bdns.py              API oficial de publicidad de subvenciones
    generic.py           páginas HTML/RSS oficiales configurables
config/
  caribdis.json
  fuentes_estatales.json
  fuentes_andalucia.json
  diputaciones.json
  ayuntamientos.json
  fuentes_europeas.json
  fundaciones.json
informes_caribdis/
  INFORME_UNICO_AYUDAS_CARIBDIS.md
  datos_caribdis.json
  historico_caribdis.json
  logs/
```

## Flujo de datos

1. La CLI determina el periodo y carga la configuración.
2. Cada adaptador devuelve oportunidades normalizadas o incidencias; un fallo no detiene los demás.
3. Los extractores completan únicamente datos explícitos y usan `Dato no localizado` en caso contrario.
4. El scoring calcula siete bloques con los máximos 25, 25, 15, 10, 10, 10 y 5.
5. El histórico fusiona resultados por identificador estable, detecta cambios y estima recurrencia solo cuando existen antecedentes.
6. El informe ordena por estado, puntuación, cercanía del cierre, solicitud directa, cuantía y dificultad.
7. El TXT BOE/BOJA sigue escribiéndose mediante el comando heredado.

## Contrato de una fuente

Cada fuente configurada tiene como mínimo:

- `id`, `name`, `group` y `organization_type`.
- `url` oficial y `official_domains`.
- `territory`, `province` y `municipality` cuando proceda.
- `adapter`: `boe_boja`, `bdns`, `html` o `rss`.
- `enabled`, `timeout`, `max_items` y `rate_limit_seconds`.

El adaptador debe:

- respetar el dominio permitido;
- aplicar timeout, reintentos y pausa configurada;
- devolver enlaces oficiales normalizados;
- registrar el error y continuar si no puede consultar la fuente;
- evitar técnicas de evasión o automatización contrarias a los términos de uso.

## Compatibilidad

`scraper_boe_boja_social.py` continúa siendo un punto de entrada válido y conserva:

- argumentos `--date`, `--days`, `--output` y `--timeout`;
- salida acumulativa `informes_boe_boja_social/resultados_ayudas_sociales_boe_boja.txt`;
- resumen de GitHub Actions;
- códigos de salida existentes.

El buscador global se ejecuta mediante `buscador_caribdis.py`. El workflow global invoca ambos comandos para mantener la salida heredada y actualizar el informe único.

## Limitaciones deliberadas

- Las páginas dinámicas sin API, RSS o HTML rastreable se registran como fuentes que requieren ajuste; no se simula su contenido.
- La configuración inicial puede apuntar a páginas oficiales de convocatorias, pero no garantiza que todos los portales mantengan una estructura estable.
- Las estimaciones de recurrencia se basan exclusivamente en ediciones guardadas y se etiquetan como estimaciones.
- El buscador no presenta una convocatoria como abierta si no localiza un cierre futuro o una indicación oficial de apertura.
