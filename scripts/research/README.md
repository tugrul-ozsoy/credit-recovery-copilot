# Research scripts

Used once to find and extract the liquidation-analysis exhibits in `data/cases/`. Not part of the app.

| Script | Use |
|---|---|
| `html2text.py in.htm out.txt` | EDGAR HTML to text: table cells joined with ` \| `, CSS page breaks marked `=====PAGEBREAK=====` |
| `locate.py text.txt "regex"` | Which page sections match a pattern (e.g. `Exhibit [A-Z] Liquidation Analysis`) |
| `pages.py text.txt a b [out.txt]` | Print or save page sections a..b |
| `footers.py text.txt a b` | First and last line of each page section, to find printed page numbers |
| `check_ww.py`, `check_wolf.py` | Early sum checks on the WW and Wolfspeed tables |
| `waterfall_repro.py` | The first 25-line naive waterfall that showed WW and Wolfspeed reproduce and Enviva does not |
