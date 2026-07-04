# Scraper BOE/BOJA de ayudas sociales

Este scraper revisa cada dia el BOE y el BOJA para detectar subvenciones o ayudas con indicios de estar dirigidas a entidades sociales, asociaciones, fundaciones, ONG, tercer sector o programas de accion social.

## Archivos

- `scraper_boe_boja_social.py`: programa principal.
- `.github/workflows/revisar-boe-boja-social.yml`: ejecucion diaria en GitHub Actions.
- `informes_boe_boja_social/ayudas_sociales_boe_boja_AAAA-MM-DD.txt`: TXT diario acumulativo.
- `informes_boe_boja_social/datos_boe_boja_social_AAAA-MM-DD.json`: datos estructurados de la revision.
- `informes_boe_boja_social/resumen_ultima_revision.md`: resumen mas reciente.

## Fuentes oficiales

- BOE: indice oficial diario `https://www.boe.es/boe/dias/AAAA/MM/DD/`.
- BOJA: XML oficial de distribucion `https://www.juntadeandalucia.es/boja/distribucion/boja.xml`.

## Ejecucion manual

```powershell
python scraper_boe_boja_social.py
```

Para revisar una fecha concreta:

```powershell
python scraper_boe_boja_social.py --date 2026-07-04
```

## GitHub Actions

El workflow se ejecuta todos los dias a las 06:30 UTC. En horario peninsular suele equivaler a las 08:30 o 07:30 segun horario de verano/invierno.

Tambien puede lanzarse manualmente desde la pestana **Actions** de GitHub, indicando una fecha opcional.

## Criterio de filtro

El scraper exige que aparezcan indicios de ayuda o subvencion y, ademas, algun encaje social/no lucrativo:

- Entidades sin animo de lucro, asociaciones, fundaciones, ONG o tercer sector.
- Voluntariado, servicios sociales, inclusion social, infancia, discapacidad, mayores, migrantes, igualdad u otros ambitos sociales.

Cada resultado incluye entidad convocante, ambito, fecha de publicacion, fecha de apertura, fecha de cierre y enlace oficial. Si el cierre o la apertura no aparecen como fecha explicita, se indica expresamente.
