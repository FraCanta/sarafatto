# Architettura

La root è `wp-content` di WordPress. Il core non va modificato.

## Responsabilità

- `themes/sarafatto` gestisce presentazione, template, supporti e asset frontend.
- `plugins/sarafatto-core` possiede CPT, tassonomie, metadati, interfacce admin, impostazioni e helper.
- `docs` documenta decisioni e flussi editoriali.

Il tema verifica `function_exists()` prima di chiamare helper del plugin. Nessun template frontend definitivo per Prodotti, Occasioni o Home è incluso in questa fase.

## Plugin

- `sarafatto-core.php`: bootstrap e caricamento moduli.
- `includes/post-types.php`: CPT `sarafatto_prodotto`, supporti e form classico senza Gutenberg.
- `includes/taxonomies.php`: Categorie, Occasioni e Idee regalo associate ai Prodotti.
- `includes/meta.php`: metadati prodotto e Front Page, sanitizzazione e capability.
- `includes/term-meta.php`: metadati dei termini, UI admin, date, whitelist e rendering delle icone.
- `includes/metaboxes.php`: scheda prodotto, gallery e box della Front Page.
- `includes/helpers.php`: impostazioni, link, URL WhatsApp, validazione date, occasioni attive e flag prodotto.
- `includes/multilingual.php`: integrazione opzionale Polylang Free, query language-aware, traduzioni collegate, stringhe dinamiche e copia/sincronizzazione selettiva dei dati strutturali.
- `assets/js/product-gallery.js`, `assets/css/product-admin.css`: UI gallery caricata solo nella schermata prodotto.
- `assets/js/term-meta.js`, `assets/css/term-meta.css`: controlli icona e immagine caricati nelle schermate Occasioni/Idee regalo.
- `assets/icons/editorial-icons.svg`: sprite SVG condiviso.
- `themes/sarafatto/template-parts/components/language-switcher.php`: selettore IT/EN custom del tema; non usa output visuale Polylang.
- `themes/sarafatto/template-parts/components/`: componenti PHP globali presentazionali (pulsanti, link, titoli, note, immagini e WhatsApp); usano argomenti `get_template_part()` e escaping WordPress.
- `themes/sarafatto/header.php` e `footer.php`: header/menu responsive e footer globale. Le posizioni `primary`, `footer` e `footer-legal` sono assegnate a menu WordPress distinti per lingua da Polylang.
- `themes/sarafatto/assets/src/js/mobile-menu.js`: menu mobile vanilla isolato; gestisce focus, Escape e scroll lock, senza dipendenze UI.
- `includes/settings.php`: pagina admin e Settings API per `sarafatto_settings`.

Helper editoriali:

- `sarafatto_is_occasion_active( $term_id )` valuta il periodo inclusivo nel timezone WordPress; date assenti/invalide o invertite significano inattiva.
- `sarafatto_get_active_occasions()` restituisce i termini attivi, o array vuoto in caso di errore query.
- `sarafatto_get_product_flags( $post_id )` restituisce `is_new` e `is_featured`, false per impostazione predefinita.
- `sarafatto_get_term_icon_markup( $icon )` genera markup SVG solo per ID presenti nella whitelist.
- `sarafatto_get_gift_idea_icon( $term_id )`, `sarafatto_get_gift_idea_image_id( $term_id )` e `sarafatto_get_gift_idea_display_title( $term_id )` restituiscono valori validati per i termini Idea regalo; il titolo usa il nome del termine come fallback.

I metadati Idea regalo vivono sulla tassonomia (`sarafatto_idea_regalo_*`), compresa la descrizione estesa filtrata con `wp_kses_post`. I prodotti associati si ricavano dalla relazione nativa della tassonomia, senza meta duplicati o interfacce di collegamento manuale.

Le icone sono definite in `includes/term-meta.php` e `assets/icons/editorial-icons.svg`; per ampliarle, mantenere allineati slug, simbolo e label. I valori memorizzati sono slug whitelisted, mai markup SVG fornito dall’utente.

Polylang è opzionale e non incluso. Le API sono protette da controlli `function_exists()`. Il plugin usa filtri Free documentati per sincronizzare solo i flag prodotto e i meta strutturali dei termini; i testi restano traducibili e le immagini vengono copiate solo alla creazione. Il tema fornisce il markup dello switcher e si nasconde quando Polylang manca. Dettagli e limiti Free sono in [MULTILINGUAL.md](MULTILINGUAL.md).

## Persistenza e sicurezza

I form admin usano nonce, capability `edit_post`/`manage_categories`, sanitizzazione all’ingresso ed escaping all’output. Le immagini sono rappresentate da ID WordPress con validazione che siano allegati immagine. Le date sono stringhe `YYYY-MM-DD`, validate come date di calendario.

All’attivazione il plugin aggiunge `manage_sarafatto_settings` ai ruoli Administrator ed Editor. Non crea contenuti o termini e non ha una procedura di disinstallazione che rimuova dati.

## Dati legacy

I CPT storici `sarafatto_novita` e `sarafatto_selezione` non sono più registrati dal modello attivo. Non si esegue migrazione o cancellazione automatica. Se il database contiene record storici, serve una conversione pianificata prima di affidarsi al nuovo admin; vedi [Content model](CONTENT-MODEL.md).

## Directory del tema e regole

`themes/sarafatto/assets/src` contiene sorgenti CSS/JS; `assets/dist` è generato. `theme.json` è la fonte dei token per colori, font, scala tipografica, spacing e larghezze; CSS e Tailwind consumano le variabili WordPress generate. Registrazioni e dati appartengono al plugin, presentazione al tema. Usare prefisso `sarafatto_`, API WordPress per media e asset, escaping WordPress e nessuna creazione automatica di pagine o termini. I menu footer rendono disponibili pagine e link configurati dall’editor, compresi quelli legali, senza URL hardcoded.
