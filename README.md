# Buscador global de ayudas CARIBDIS

Buscador automático de subvenciones, ayudas a fondo perdido, premios para proyectos, programas europeos y otras oportunidades de financiación compatibles con asociaciones sin ánimo de lucro.

El proyecto mantiene el scraper histórico de BOE y BOJA y añade una arquitectura modular para consultar fuentes estatales, andaluzas, provinciales, locales, europeas, GALP/GALPA/FEMPA y fundaciones privadas.

El documento que debe revisar una persona usuaria es siempre:

`informes_caribdis/INFORME_UNICO_AYUDAS_CARIBDIS.md`

Los JSON, logs y CSV son soporte técnico para histórico, deduplicación y diagnóstico.

## Perfil de CARIBDIS

CARIBDIS es una asociación andaluza sin ánimo de lucro dedicada a:

- conservación, seguimiento y restauración de fauna, flora, especies y hábitats marinos;
- fondos, praderas, algas y ecosistemas submarinos, costeros y litorales;
- residuos marinos, contaminación, cambio climático y economía azul;
- ciencia ciudadana e investigación participativa;
- educación ambiental, divulgación y cultura científica;
- talleres y materiales accesibles para menores, juventud, alumnado NEAE y personas con discapacidad;
- inclusión social y voluntariado ambiental;
- proyectos en Andalucía, especialmente Sevilla, Málaga, Cádiz, Huelva, Almería y el litoral andaluz.

## Fuentes

La configuración inicial incluye:

- BOE y BOJA mediante el scraper heredado.
- API oficial de la Base de Datos Nacional de Subvenciones, BDNS.
- FECYT, Fundación Biodiversidad, MITECO, ministerios sociales, INJUVE, Ministerio de Ciencia, Agencia Estatal de Investigación, Educación, Cultura y Programa Pleamar.
- Consejerías y organismos de la Junta de Andalucía.
- Las ocho diputaciones andaluzas.
- Capitales andaluzas y los municipios costeros enumerados en `config/ayuntamientos.json`.
- GALPA de Cádiz y Huelva, GALPA Málaga, Alborán y Almería a Levante, junto con los procedimientos FEMPA de la Junta.
- Funding & Tenders, LIFE, Horizon Europe, Misiones, Biodiversa+, Erasmus+, Cuerpo Europeo de Solidaridad, POCTEP, Sudoe, Euro-MED, Atlantic Area, EMFAF, Europa Creativa, CERV, FSE+, FEDER y EUKI.
- Fundación la Caixa, CaixaBank, Unicaja, ONCE, Carasso, Banco Santander, Ibercaja, Endesa, Naturgy, Moeve, Repsol, Telefónica y MAPFRE.

Solo se consultan los dominios indicados en `official_domains`. Cada fuente declara una cobertura `historical`, `api`, `rss`, `current` o `landing`. El informe muestra el alcance real y no atribuye 365 días de revisión a una portada que solo refleja su estado actual.

Las fuentes con páginas dinámicas o sin un listado estable llevan `requires_adjustment: true`. Están desactivadas por defecto y aparecen en `Fuentes pendientes de adaptación`, sin producir oportunidades rankeadas. Solo se ejecutan deliberadamente con `--experimental`.

## Scoring CARIBDIS

Cada oportunidad recibe una puntuación de 0 a 100:

| Bloque | Máximo |
|---|---:|
| Elegibilidad de CARIBDIS | 25 |
| Encaje temático | 25 |
| Encaje social y educativo | 15 |
| Encaje territorial | 10 |
| Tipo de financiación | 10 |
| Estado y plazo | 10 |
| Viabilidad para una asociación nueva | 5 |

Prioridades:

| Puntuación | Prioridad |
|---:|---|
| 85-100 | Muy alta |
| 70-84 | Alta |
| 50-69 | Media |
| 25-49 | Baja |
| 0-24 | Descartar |

La forma de participación distingue:

- `Solicitud directa`
- `Solo con socio`
- `Socia de ayuntamiento`
- `Socia de universidad o centro científico`
- `Socia de consorcio europeo`
- `Vigilar próxima edición`
- `No elegible`

Las concesiones directas nominativas, beneficiarios únicos, becas o premios personales, contratos, licitaciones y nombramientos se descartan. Las ayudas exclusivas de ayuntamientos, universidades, organismos públicos, empresas o sector pesquero no se eliminan automáticamente: se clasifican como oportunidades con socio cuando existe encaje para CARIBDIS.

### Umbral temático mínimo

Una ayuda solo puede alcanzar prioridad Media, Alta o Muy alta si acredita al menos uno de estos encajes:

- conservación, biodiversidad, fauna, flora, hábitats, litoral, contaminación o restauración marina;
- ciencia ciudadana, divulgación científica, cultura científica o educación ambiental;
- talleres o actividades expresamente científicas o ambientales para menores, discapacidad, NEAE o colectivos vulnerables.

Las menciones aisladas a infancia, vulnerabilidad, asociaciones, educación genérica o responsabilidad social no superan el umbral. Su puntuación queda limitada a 49 y su prioridad a Baja o Descartar.

FECYT Cultura Científica utiliza el adaptador `verified`: la ficha 2026 se construye con fechas, beneficiarios y condiciones revisados en su portal y bases oficiales, no con palabras de una portada.

## Informe único

El informe se sobrescribe en cada ejecución e incluye, en orden:

1. fecha y periodo;
2. resumen ejecutivo e incidencias;
3. ayudas abiertas;
4. ayudas próximas;
5. cerradas recurrentes;
6. Unión Europea;
7. estatales;
8. Junta;
9. diputaciones;
10. ayuntamientos;
11. GALP/GALPA/FEMPA;
12. fundaciones;
13. solicitud directa;
14. socio municipal;
15. socio científico;
16. consorcio europeo;
17. descartadas;
18. calendario a tres, seis y doce meses;
19. ranking completo;
20. recomendaciones inmediatas.

El ranking ordena primero convocatorias abiertas y directas de prioridad Muy alta o Alta, después abiertas de prioridad Media, próximas o recurrentes y, a continuación, oportunidades que requieren socio. Las ayudas de prioridad Baja sin umbral temático no entran en los Top 10. Las descartadas aparecen exclusivamente en la sección 17.

## Histórico y cambios

`informes_caribdis/historico_caribdis.json` conserva el histórico estructurado. El sistema:

- deduplica por URL oficial canónica e identificador de fuente;
- detecta cambios de apertura, cierre, presupuesto, importe y estado;
- marca reaperturas;
- compara títulos equivalentes de distintas ediciones;
- estima una próxima fecha solo cuando existen ediciones en al menos dos años.

Toda fecha estimada se presenta con el prefijo `Estimación histórica:` y no se confunde con una publicación oficial.

## Ejecución local

No requiere paquetes externos. Se recomienda Python 3.12.

Revisar los últimos diez días:

```shell
python buscador_caribdis.py
```

Indicar fecha final y número de días:

```shell
python buscador_caribdis.py --date 2026-07-26 --days 30
```

Indicar un intervalo exacto:

```shell
python buscador_caribdis.py --start-date 2026-01-01 --end-date 2026-07-26
```

Revisión histórica de 365 días:

```shell
python buscador_caribdis.py --historical
```

La opción fija el periodo solicitado, pero solo BOE/BOJA y las APIs con fechas y paginación pueden acreditar cobertura histórica completa. RSS, listados actuales y portadas informan su cobertura limitada en el propio informe.

Diagnosticar una fuente concreta:

```shell
python buscador_caribdis.py --source-id bdns
```

Ejecutar deliberadamente una fuente pendiente de adaptación:

```shell
python buscador_caribdis.py --source-id eu_funding_tenders --experimental
```

Mantener únicamente la salida heredada de BOE/BOJA:

```shell
python scraper_boe_boja_social.py --date 2026-07-26 --days 10
```

Ejecutar pruebas:

```shell
python -m unittest -v
```

## GitHub Actions

El workflow `Revisar ayudas globales CARIBDIS` se ejecuta cada día a las 06:30 UTC y también manualmente.

La ejecución manual permite:

- `start_date` y `end_date`;
- `days`;
- `historical`;
- `source_id` para diagnóstico.

El workflow diario conserva la revisión BOE/BOJA, actualiza el buscador global y solo crea un commit cuando cambian los informes. El resumen de GitHub Actions muestra oportunidades, fuentes correctas e incidencias.

El workflow independiente `Pruebas` se activa en `push` y `pull_request` y ejecuta únicamente:

```shell
python -m unittest -v
```

## Añadir una fuente

Las fuentes se distribuyen en:

- `config/fuentes_estatales.json`
- `config/fuentes_andalucia.json`
- `config/diputaciones.json`
- `config/ayuntamientos.json`
- `config/fuentes_galp.json`
- `config/fuentes_europeas.json`
- `config/fundaciones.json`

Ejemplo:

```json
{
  "id": "fuente_unica",
  "name": "Nombre visible",
  "group": "Ayuntamientos y entidades locales",
  "adapter": "html",
  "url": "https://www.organismo-oficial.es/convocatorias/",
  "official_domains": ["organismo-oficial.es"],
  "organization": "Organismo",
  "organization_type": "Ayuntamiento",
  "territory": "Andalucía",
  "province": "Cádiz",
  "municipality": "Ejemplo",
  "coverage_type": "current",
  "coverage_note": "Listado oficial actual; no ofrece histórico completo.",
  "max_items": 20,
  "enabled": true
}
```

Los archivos con muchas fuentes admiten `defaults` y `sources`, como `config/ayuntamientos.json`; para añadir un municipio basta con incorporar una entrada corta en `sources`.

Adaptadores disponibles:

- `bdns`: API oficial de BDNS.
- `html`: página de convocatorias o ayudas.
- `rss`: feed RSS o Atom.
- `verified`: ficha de convocatoria con metadatos revisados y páginas oficiales comprobadas.

## Robustez

- Tres reintentos por defecto y timeout configurable.
- Ejecución concurrente con límite de workers.
- Comprobación de `robots.txt`.
- Restricción a dominios oficiales configurados.
- Pausa configurable entre páginas de detalle.
- Caché opcional por fuente mediante `cache_ttl_seconds`.
- Continuación del proceso si una fuente falla.
- `Dato no localizado` cuando la página no publica un valor.
- Incidencias guardadas en el informe, en GitHub Actions y en `informes_caribdis/logs/ultima_ejecucion.json`.

## Limitaciones conocidas

- Un portal dinámico puede requerir un adaptador API específico; se marca con `requires_adjustment`.
- La lectura genérica de HTML no sustituye la revisión humana de las bases.
- PDF escaneados, formularios con autenticación y buscadores JavaScript pueden no exponer datos.
- La elegibilidad, cofinanciación y gastos deben confirmarse siempre en el enlace oficial.
- Las fuentes privadas pueden cambiar su estructura o condiciones sin aviso.

La arquitectura y decisiones de compatibilidad están documentadas en `docs/ARQUITECTURA.md`.
