# Design system

Il design system del tema Saràfatto è editoriale, fotografico e contemporaneo. La selezione dei prodotti è il contenuto distintivo: i componenti globali restano essenziali e non aggiungono card o decorazioni senza necessità.

## Fonte dei token

[`themes/sarafatto/theme.json`](../themes/sarafatto/theme.json) è la fonte unica per palette, famiglie e scala tipografica, spacing Gutenberg e larghezze dei layout. WordPress espone questi valori come `--wp--preset--*`; `assets/src/css/app.css` crea alias semantici per i template, mentre `tailwind.config.js` punta alle stesse variabili. Radius, bordi, motion e livelli di sovrapposizione, non presenti come preset WordPress, sono definiti una sola volta in `:root` nel CSS.

## Palette

| Token | Valore | Uso |
| --- | --- | --- |
| White | `#FFFFFF` | Fondo globale, header e testo sul footer |
| Ink | `#1A1A1A` | Testo, footer e pulsante primario |
| Turquoise / brand | `#00A79D` | Firma identitaria e underline hover |
| Pink | `#E91E8E` | Accento editoriale puntuale |
| Yellow | `#FFC942` | Evidenziazione e note |
| Muted | `#6F6A64` | Testi secondari |

Il bianco è il background principale di body, header, main, pagine editoriali, archive, single e futura Home. Il precedente avorio `#FDF7EE` non è più un token attivo e non va riutilizzato come fondo predefinito. Ink definisce testo, CTA e footer scuro; Turchese firma il brand, Pink marca dettagli editoriali e Yellow evidenzia note occasionali. Non usare gli accenti insieme senza una ragione compositiva. `--color-border` è una linea Ink con opacità controllata; il focus usa Ink su fondo chiaro e White nel footer scuro.

## Tipografia

- **Fraunces** per titoli e display.
- **Manrope** per corpo e interfaccia.
- Entrambe le famiglie hanno fallback di sistema e `font-display: swap`.
- La scala fluida in `theme.json` comprende `display-xl`, `display-lg`, `h1`, `h2`, `h3`, `body-lg`, `body`, `small`, `eyebrow` e `caption`. Le prime sei misure scalano con il viewport.

I font WOFF2 non sono inclusi. Aggiungerli in `themes/sarafatto/assets/fonts/fraunces/fraunces-variable.woff2` e `themes/sarafatto/assets/fonts/manrope/manrope-variable.woff2`; i relativi `@font-face` sono già predisposti in `assets/src/css/app.css`. Non caricare font da CDN.

## Spazi e layout

La scala condivisa è 4, 8, 12, 16, 24, 32, 48, 64, 96 e 128 px (token `1, 2, 3, 4, 6, 8, 12, 16, 24, 32`). `--gutter` è fluido e adotta la stessa scala.

- `content`: 48rem, testo e contenuti leggibili.
- `wide`: 80rem, sezioni editoriali.
- `full`: larghezza disponibile, senza forzare `100vw`.

Usare `.container`, `.container--content` e `.container--full`. Le immagini devono passare da API WordPress responsive quando possibile.

## Radius, bordi e motion

I radius di superfici e dettagli restano 2px e 4px; i button hanno il token condiviso `--radius-pill` (9999px). Le superfici preferiscono linee, underline e contrasto tipografico alle card. Token motion: `--duration-fast` (120ms), `--duration-normal` (180ms), `--duration-slow` (320ms), `--duration-menu` (550ms), `--easing-standard`, `--easing-soft` e `--easing-menu`. Applicare transizioni solo a stati interattivi; `prefers-reduced-motion` riduce transizioni e animazioni.

## Focus e accessibilità

`:focus-visible` usa un contorno Ink di 2px su fondo chiaro e White nel footer scuro, con offset di 4px. Non rimuoverlo senza un equivalente visibile. Il tema include skip link, landmark semantici, etichette nav, switcher IT/EN con `aria-current`, e menu mobile con Escape, focus trap, blocco dello scroll e ripristino del focus.

La gerarchia z-index è contenuto `0`, pannello overlay `10`, header `20`, controlli header (logo, trigger e WhatsApp) `30`, skip link `40`. Il WordPress admin bar mantiene il proprio livello nativo sopra l’interfaccia; da loggati il pannello si posiziona sotto la barra (32px oltre 782px, 46px fino a 782px).

## Componenti riutilizzabili

I template in `themes/sarafatto/template-parts/components/` accettano argomenti tramite `get_template_part( ..., null, $args )`:

- `button.php`: varianti `primary`, `secondary`, `text`; accetta label, URL o stato disabilitato, icona testuale opzionale e link esterno.
- `text-link.php`: link editoriale con freccia opzionale.
- `eyebrow.php`: micro-label.
- `editorial-heading.php`: tag h1–h6, scala semantica, accento ammesso e classi aggiuntive; il testo è escaped, non accetta HTML arbitrario.
- `section-intro.php`: composizione di eyebrow, titolo e introduzione.
- `image-frame.php`: ID allegato, alt, rapporto, object-fit e didascalia; l’immagine viene renderizzata con `wp_get_attachment_image()`.
- `editorial-note.php`: nota con accento controllato.
- `whatsapp-link.php`: usa gli helper del plugin per numero, messaggio, lingua e titolo prodotto; non genera URL senza helper/configurazione.
- `language-switcher.php`: componente Polylang esistente, mantenuto e stilizzato senza bandiere o dropdown.

Il testo dei componenti viene escaped. Le etichette dell’interfaccia globale sono fornite in italiano e inglese da `sarafatto_theme_label()` in base alla lingua corrente; i menu WordPress sono invece tradotti e assegnati per lingua. Per i contenuti rich text, `section-intro` consente solo il markup filtrato da `wp_kses_post()`.

## Button system

`template-parts/components/button.php` è la source of truth per ogni CTA con contenitore. Non sono ammessi stili one-off: i template passano al componente variante, dimensione, icona e URL/stato. I pulsanti Gutenberg condividono la stessa base CSS.

Il blocco core Pulsante usa la stessa base e offre gli stili selezionabili **SaràFatto · Primario**, **Accento**, **Secondario** e **Testuale**. Le classi di taglia `button--sm`, `button--md` e `button--lg` applicano i token del componente anche al link interno del blocco. L’icona di freccia usa lo stesso glifo Iconify MDI `arrow-top-right` del componente PHP.

| Variante | Aspetto | Uso |
| --- | --- | --- |
| `primary` | Ink `#1A1A1A`, testo White | CTA principale |
| `accent` | Giallo `#FFC942`, testo Ink | CTA evidenziata su fondi scuri |
| `secondary` | Fondo trasparente, bordo Ink da 1px, testo Ink | Azione alternativa |
| `text` | Nessun contenitore, underline editoriale | Link che non richiede un pulsante |

Le size `sm`, `md` e `lg` cambiano solo font e padding; `md` è il default. Font-size: `clamp(0.875rem, 0.8vw, 1rem)`, `clamp(0.95rem, 0.9vw, 1.075rem)` e `clamp(1rem, 1vw, 1.15rem)`. Tutte le varianti con contenitore usano `--radius-pill: 9999px`, altezza minima 44px e lo stesso gap icona/testo (`--button-icon-gap`). Su mobile la size mantiene il target di 44px. L’icona è opzionale, può precedere o seguire il testo, è decorativa per gli screen reader ed è allineata al centro. Le icone Iconify usano il plugin Tailwind 3 e il set Material Design (`mdi`) installato nel tema.

L’hover è condiviso e leggero: primary passa a Turchese/Ink, secondary si inverte; le icone possono traslare di 2px. `:focus-visible` mantiene un contorno Ink visibile con offset. Il controllo icon-only mobile riusa i token di radius, focus e touch target e conserva la label per gli screen reader. I link editoriali senza box restano `text-link`/`button--text`, non ricevono radius visibili.

## Header e navigazione

## Header desktop

Il container resta largo il 90% del viewport, senza max-width desktop. Da `80rem` (1280px) il layout usa `grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)`: menu allineato a sinistra, logo centrato nella colonna `auto`, azioni allineate a destra. Il burger non compare su desktop. Le azioni sono un gruppo flex nell’ordine **WhatsApp → IT / EN**, con gap fluido 20–28px. La CTA WhatsApp passa dal componente button globale (`primary`, `sm`) e dal helper URL del plugin; non contiene numero o URL hardcoded. La versione IT/EN usata nel drawer mobile è contenuta nel pannello stesso, così accompagna lo slide e non appare prima dell’apertura.

Il logo mantiene proporzioni naturali e scala da 120px a 150px (`clamp(7.5rem, 7vw, 9.375rem)`). La nav usa Manrope, peso 450 e `clamp(1.0625rem, 0.95vw, 1.1875rem)` (17–19px), con gap `clamp(1.75rem, 2vw, 2.5rem)` (28–40px). IT / EN usa una misura fluida fino a 18px, lingua corrente sottolineata e slash attenuata. Sotto `80rem` il layout passa alla composizione mobile con burger, logo e WhatsApp icon-only; il pannello mobile mantiene lo slide fullscreen e la chiusura prima della navigazione.

Hover e focus rivelano una linea sottile Turchese; la pagina corrente e i suoi antenati usano una linea Pink persistente. Il segno non dipende dal solo colore. Lo switcher IT / EN mantiene il componente custom, la scala del menu e una separazione slash attenuata. Il menu mobile resta gestito dal pannello accessibile vanilla già descritto sopra.

## Regole responsive

Approccio mobile-first con breakpoint desktop dell’header a `80rem` (1280px) e una correzione footer per schermi molto stretti. Verificare almeno 320, 375, 390, 430, 768, 1024, 1280, 1440, 1920 e 2560px. Tenere immagini e contenitori dentro la larghezza disponibile ed evitare `100vw`/`w-screen`.
