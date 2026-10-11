# Modello contenuti

Il contenuto principale è il **Prodotto**, registrato come CPT `sarafatto_prodotto` con archivio `/prodotti/`. Il plugin non crea prodotti, pagine o termini all’attivazione. La schermata prodotto usa un form classico guidato; Gutenberg è disabilitato per questo CPT.

Pagine, Prodotti e le tre tassonomie sono predisposti per le traduzioni IT/EN con Polylang Free. Vedi [Architettura multilingua](MULTILINGUAL.md) per abilitazione, sincronizzazione dei dati strutturali e fallback.

## Prodotto

- Titolo: `post_title`.
- Immagine principale: Featured Image WordPress.
- Etichetta editoriale: `sarafatto_editorial_label`.
- Breve descrizione: excerpt nativo `post_excerpt`.
- Racconto: `sarafatto_story` (HTML filtrato con `wp_kses_post`).
- Gallery facoltativa: `sarafatto_gallery`, array di ID immagine della Media Library.
- Prezzo facoltativo: `sarafatto_price`, importo numerico normalizzato con due decimali, senza simbolo valuta né formattazione.
- SKU / Codice prodotto facoltativo: `sarafatto_sku`, stringa sanitizzata fino a 100 caratteri.
- Novità: `sarafatto_is_new`, booleano, default `false`.
- In evidenza: `sarafatto_is_featured`, booleano, default `false`.

Il prezzo accetta input con virgola o punto decimale (ad esempio `28`, `28,50` o `28.50`), rimuove gli spazi e salva una stringa numerica canonica (`28.00`, `28.50`). Un valore non valido non sovrascrive quello già salvato e genera un avviso nell’admin; un campo vuoto rimuove il meta. `sarafatto_format_price( $price )` restituisce il prezzo formattato secondo la localizzazione WordPress corrente (ad esempio `28,00 €`) oppure una stringa vuota se il valore manca/non è valido. `sarafatto_get_product_price( $post_id )` restituisce il valore canonico o una stringa vuota. Il frontend può quindi omettere il prezzo quando l’helper non restituisce un valore.

Prezzo e SKU appartengono a ciascun post prodotto tradotto: Polylang non li copia e non li sincronizza automaticamente. Le traduzioni possono quindi avere lo stesso prezzo/SKU inserito manualmente oppure valori diversi.

Questi campi preparano una possibile migrazione futura, senza attivare WooCommerce. Mappatura prevista:

| Modello SaràFatto | WooCommerce |
| --- | --- |
| `sarafatto_prodotto` | Prodotto WooCommerce |
| `sarafatto_price` | `_regular_price` |
| `sarafatto_sku` | `_sku` |
| Immagine in evidenza | Immagine prodotto |
| `sarafatto_gallery` | Gallery prodotto |
| `sarafatto_categoria` | `product_cat` |
| `sarafatto_occasione`, `sarafatto_idea_regalo` | Possono restare tassonomie custom |

I flag sono indipendenti. I prodotti iniziali non diventano Novità automaticamente. Nel frontend futuro, Novità e In evidenza saranno query di prodotti con il rispettivo flag attivo.

## Classificazioni

Le tre tassonomie gerarchiche sono associate ai Prodotti e i termini si creano liberamente dal backend:

- `sarafatto_categoria` — Categorie, per classificare il tipo di prodotto;
- `sarafatto_occasione` — Occasioni, con archivio/pubblicazione indipendenti dalle date editoriali;
- `sarafatto_idea_regalo` — Idee regalo.

Nessun termine come Natale o Estate è predefinito o codificato nel plugin.

### Immagine editoriale Categorie

Ogni termine `sarafatto_categoria` mantiene nome, slug e descrizione WordPress e può avere un’immagine editoriale facoltativa salvata come ID allegato in `sarafatto_category_image_id`. Il campo usa la Media Library e il valore è recuperabile con `sarafatto_get_category_image_id( $term_id )`; se il termine o l’immagine non esistono, l’helper restituisce `0`. Ogni termine tradotto può avere un’immagine propria: il plugin non sincronizza questo meta tra italiano e inglese. Il contenuto è predisposto per la futura sezione Home “Piccole grandi scoperte” e per l’archivio della singola categoria; la presentazione frontend non è implementata in questa fase.

### Metadati Occasioni

Ogni termine può avere icona (`sarafatto_occasion_icon`), immagine editoriale (`sarafatto_occasion_image`, ID allegato), titolo (`sarafatto_occasion_title`), introduzione (`sarafatto_occasion_intro`), data inizio e data fine (`sarafatto_occasion_start_date`, `sarafatto_occasion_end_date`, formato `YYYY-MM-DD`).

Le date sono facoltative per il termine, ma senza entrambe valide l’Occasione non è considerata attiva. `sarafatto_is_occasion_active( $term_id )` include entrambi i giorni limite e usa la data corrente nel timezone WordPress. Una data non valida o un inizio successivo alla fine rende inattiva solo la promozione: il termine, l’archivio e i prodotti associati non vengono nascosti o modificati.

### Metadati Idee regalo

`sarafatto_idea_regalo` è una tassonomia editoriale libera associata ai Prodotti. Ogni termine mantiene nome e slug WordPress e può avere:

- `sarafatto_idea_regalo_icon`: icona obbligatoria scelta dal set controllato;
- `sarafatto_idea_regalo_image`: ID di un allegato immagine della Media Library;
- `sarafatto_idea_regalo_title`: titolo editoriale opzionale; nel frontend futuro prevale sul nome del termine, che resta il fallback;
- `sarafatto_idea_regalo_intro`: breve introduzione testuale;
- `sarafatto_idea_regalo_description`: descrizione estesa facoltativa, filtrata con `wp_kses_post`.

Sara assegna le Idee regalo dalla scheda Prodotto tramite la tassonomia. Non esiste una relazione duplicata in post meta o un selettore di prodotti nel termine. La futura pagina pubblica del termine, ad esempio `/idee-regalo/per-lei/`, potrà mostrare icona, titolo, immagine, introduzione, descrizione e prodotti assegnati; il layout resta responsabilità del tema.

Le Idee regalo sono raccolte editoriali permanenti: non hanno date, programmazione o attivazione automatica. Le Occasioni, invece, possono avere date inizio/fine e risultare attive automaticamente per la promozione Home.

### Set icone

Occasioni e Idee regalo condividono il set controllato `sparkles`, `gift`, `heart`, `sun`, `flower`, `star`, `home`, `bag`, `party`, `leaf`. Le etichette e la whitelist sono in `plugins/sarafatto-core/includes/term-meta.php`; le forme SVG sono simboli nell’unico sprite `plugins/sarafatto-core/assets/icons/editorial-icons.svg`. `sarafatto_get_term_icon_markup()` emette il riferimento al simbolo validato. Per aggiungere icone si aggiorna sia la whitelist sia lo sprite.

## Home futura

La Home definitiva non è implementata. La logica editoriale prevista è:

- Novità: prodotti con `sarafatto_is_new = true`;
- In evidenza: prodotti con `sarafatto_is_featured = true`;
- Occasione: una o più occasioni restituite da `sarafatto_get_active_occasions()`.

Se non ci sono occasioni attive, il tema potrà omettere la sezione. `sarafatto_get_product_flags( $post_id )` restituisce entrambi i flag, entrambi `false` per un ID non prodotto.

## Pagine e impostazioni

Le pagine Home, Il negozio, Idee regalo, Personalizzati, Spedizioni e Contatti si creano manualmente. L’opzione `sarafatto_settings` contiene contatti, orari, social, spedizioni e ID delle pagine collegate. Solo la Front Page mostra il box con eyebrow e CTA. La presentazione rimane responsabilità del tema.

## Dati preesistenti

Il modello non registra più i CPT `sarafatto_novita` e `sarafatto_selezione`, né le loro interfacce. I record eventualmente presenti nel database non vengono eliminati; senza la registrazione del vecchio post type possono però non essere raggiungibili dall’admin. Questa modifica non esegue conversioni automatiche: prima di usare il nuovo modello su un sito con contenuti esistenti, esportare/verificare i record e convertire manualmente le vecchie Novità in Prodotti, riclassificando categorie e mappando i campi editoriali. Le vecchie Selezioni richiedono una decisione editoriale perché Occasioni sono termini, non raccolte di post autonome. Non è stato possibile verificare il database locale in questo ambiente.
