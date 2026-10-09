# Architettura multilingua IT / EN

Polylang Free è il layer di lingua e traduzione; il tema mantiene controllo su markup e aspetto del selettore. Polylang non è incluso nella repository: installarlo manualmente dal pannello Plugin di WordPress. Nel checkout verificato non è presente `wp-content/plugins/polylang`, perciò configurazione e test runtime con Polylang restano da fare in Local.

## Configurazione in Local

In Languages → Languages aggiungere **Italiano** (`it`) e **English** (`en`), impostare Italiano come lingua predefinita e in Languages → Settings scegliere l’URL con codice lingua. Attivare l’opzione per nascondere il codice lingua predefinito, se disponibile nella configurazione selezionata. Assegnare Italiano ai contenuti già presenti prima di creare le traduzioni inglesi.

In Languages → Settings → Custom post types and Taxonomies abilitare `sarafatto_prodotto` e le tassonomie `sarafatto_categoria`, `sarafatto_occasione`, `sarafatto_idea_regalo`. Sono pubbliche e registrate tramite le API WordPress standard, quindi Polylang Free può esporle nel modulo. Le Pagine WordPress sono gestite nativamente. Creare e collegare le traduzioni dalla colonna/metabox Languages di Polylang; assegnare i menu Primary IT ed EN nelle impostazioni menu per lingua.

Le basi di rewrite restano quelle WordPress/Saràfatto (`prodotti`, `categoria`, `occasioni`, `idee-regalo`) anche nelle URL inglesi, con il normale prefisso lingua quando configurato. Non vengono inventate basi tradotte tramite rewrite personalizzate: la traduzione dei permalink base per CPT e tassonomie è una funzione Polylang Pro. Dopo la configurazione salvare Impostazioni → Permalink.

## Contenuto e dati strutturali

Titoli, excerpt, racconto prodotto e metadati editoriali dei termini sono contenuti distinti per lingua dopo la creazione della traduzione. La descrizione nativa del termine Occasione è il campo descrizione WordPress. Polylang collega i prodotti, le pagine e i termini tradotti; non vengono creati campi `_it`/`_en`.

Il plugin usa i filtri Polylang documentati `pll_copy_post_metas`, `pll_copy_term_metas` e `pll_copy_taxonomies`:

- sincronizza tra traduzioni prodotto `sarafatto_is_new` e `sarafatto_is_featured`;
- sincronizza tra Occasioni icona, data inizio e data fine;
- sincronizza tra Idee regalo l’icona;
- copia in creazione Featured Image, gallery e immagini editoriali dei termini, senza aggiungerle alla lista di sincronizzazione successiva;
- include le tre tassonomie prodotto nel flusso di copia: Polylang usa le relazioni tra termini tradotti; se la traduzione del termine non esiste, non viene introdotta una relazione manuale al termine della lingua sorgente.

Etichetta, excerpt, racconto, titoli e testi dei termini restano modificabili per lingua. Non abilitare la sincronizzazione globale di tutti i custom fields se si vogliono conservare questi testi diversi: i filtri del plugin limitano la sincronizzazione Saràfatto ai soli dati strutturali indicati.

Le immagini sono ID allegato condivisi, non copie fisiche. La copia iniziale è una base: in seguito ogni traduzione può avere ID immagine/gallery differenti. Lasciare disattivata l’eventuale sincronizzazione nativa permanente della Featured Image nelle impostazioni Polylang se si vuole poter differenziare l’immagine principale dopo la copia iniziale.

## Helper e query

`includes/multilingual.php` fornisce:

- `sarafatto_is_polylang_active()`;
- `sarafatto_get_current_language()` (fallback `it`);
- `sarafatto_get_translation_id( $id, 'post'|'term', $lang )` e `sarafatto_get_translation_url(...)`, che non sostituiscono una traduzione mancante con l’originale;
- `sarafatto_add_language_to_query_args( $args )`, che aggiunge il `lang` documentato solo se Polylang è attivo;
- `sarafatto_get_language_switcher_items()` per il componente tema;
- `sarafatto_get_product_whatsapp_url( $post_id )`, che usa il titolo nella lingua corrente e una stringa-base traducibile.

`sarafatto_get_active_occasions()` usa l’helper query e il timezone WordPress già previsto. Le future `WP_Query` di Home/Novità/In evidenza dovranno chiamare `sarafatto_add_language_to_query_args()` oppure affidarsi alla lingua della query principale. Le stringhe globali testuali selezionate (orari, messaggio WhatsApp, titolo/testo/zona spedizioni) vengono registrate nel gruppo String Translations **Saràfatto**; telefono, email, indirizzo, WhatsApp number e social restano nell’unica option globale.

## Language switcher custom

`themes/sarafatto/template-parts/components/language-switcher.php` usa soltanto helper Saràfatto e non chiama `pll_the_languages`, widget, shortcode o markup Polylang. Presenta IT / EN, rende la lingua corrente come testo con `aria-current="page"`, aggiunge `lang` e `hreflang` al link alternativo e disabilita semanticamente la scelta quando non esiste la traduzione equivalente. Non invia l’utente alla Home come fallback. Il template part è riutilizzabile da header e futura navigazione mobile; il tema attuale lo include nell’header esistente.

Se Polylang è disattivato o le due lingue non sono configurate, il componente non produce markup. Le funzioni tornano alla lingua predefinita italiana, non chiamano API mancanti e lasciano funzionare WordPress standard. I contenuti EN già creati restano contenuti WordPress e non vengono eliminati dalla disattivazione; prima di disattivare Polylang in produzione occorre considerare che WordPress da solo non applica più il filtro lingua.

## SEO e limiti Free

Polylang gestisce lingua URL, lingua HTML e segnali hreflang/canonical/sitemap nei flussi supportati dal plugin e dall’eventuale plugin SEO installato. Il tema non duplica una suite SEO né forza URL. Polylang Free non traduce le basi URL di CPT/tassonomie né offre le funzioni Pro di sincronizzazione post. Il plugin applica solo i filtri di copia/sincronizzazione documentati disponibili in Free; la loro verifica effettiva richiede Polylang installato.
