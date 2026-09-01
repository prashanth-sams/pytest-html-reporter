# Vendored libraries

The report used to pull these off a CDN, which meant a run on a machine with no
way out to the internet produced a blank white page - jQuery never arrived and
nothing after it ran. They ship here instead, verbatim as published, and
[`html_page/assets.py`](../assets.py) writes them into the report so it opens
anywhere.

| File | Version | Licence |
| --- | --- | --- |
| `jquery.min.js` | 3.5.1 | MIT |
| `jquery.dataTables.min.js` / `.css` | DataTables 1.10.19 | MIT |
| `dataTables.buttons.min.js`, `buttons.dataTables.min.css` | Buttons 1.5.2 | MIT |
| `buttons.html5.min.js`, `buttons.print.min.js` | Buttons 1.5.2 | MIT |
| `buttons.colVis.min.js` | Buttons 1.6.1 | MIT |
| `bootstrap.min.js` / `.css` | Bootstrap 4.1.3 | MIT |
| `chart.min.js` | Chart.js 2.8.0 | MIT |
| `jspdf.min.js` | jsPDF 1.3.2 | MIT |
| `dom-to-image.min.js` | dom-to-image 2.6.0 | MIT |
| `jszip.min.js` | JSZip 3.1.3 | MIT or GPLv3 (used under MIT) |

fancyBox is deliberately **not** here. The screenshot gallery used fancyBox
3.5.7, which is GPLv3 or a paid commercial licence - either way not something an
MIT-licensed package can redistribute. The report opens screenshots with a
lightbox of its own instead, in `template.html`.

To move a version on, replace the file and update the row above; the load order
lives in `assets.py`, not here.
