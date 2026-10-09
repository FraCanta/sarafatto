# Sviluppo

## Ambiente

La repository è `wp-content` di Local. Avviare il sito in Local e accedere al backend WordPress.

## Attivazione e contenuti

Attivare **Saràfatto Core** e il tema **Saràfatto**. L’attivazione non crea pagine, prodotti o termini. L’Editor e l’Administrator possono usare la pagina Impostazioni Saràfatto.

### Configurare IT / EN

Installare manualmente **Polylang Free** da Plugin → Aggiungi nuovo (non è incluso nel progetto). In Languages → Languages creare Italiano (`it`) come lingua predefinita e English (`en`) come secondaria. Assegnare Italiano ai contenuti già presenti. In Languages → Settings configurare gli URL con lingua e nascondere il codice della lingua predefinita. Abilitare nella sezione Custom post types and Taxonomies Prodotti e Categorie, Occasioni e Idee regalo. Polylang Free mantiene le basi URL custom non tradotte. Per ogni pagina/prodotto/termine usare le icone/colonne Languages per creare e collegare la traduzione; non copiare il termine italiano nell’assegnazione del prodotto inglese. Creare un menu per lingua e assegnarlo alla posizione Primary corrispondente. Lo switcher custom è nel template part del tema e non va aggiunto ai menu.

In Languages → String translations tradurre le stringhe del gruppo **Saràfatto**, incluso il modello di messaggio WhatsApp. I contatti e i link social restano globali e non duplicati. Tradurre le etichette del tema tramite i file lingua gettext del text domain `sarafatto`.

### Menu del tema

In Aspetto → Menu creare menu per ciascuna lingua e assegnarli alle posizioni **Menu principale**, **Menu footer** e **Menu legale footer**. Polylang associa le posizioni alle lingue: configurare un menu distinto per IT e EN in modo che voci e destinazioni restino tradotte. La navigazione principale non ha voci hardcoded; il menu legale può contenere le pagine Privacy, Cookie e gli eventuali termini già pubblicati. L’header include uno switcher lingua custom; non aggiungerlo al menu WordPress.

Su mobile il menu principale apre un pannello a schermo intero con switcher lingua. Il menu è utilizzabile anche senza JavaScript, quando resta mostrato nel flusso della pagina.

Per creare contenuti editoriali:

1. Da **Prodotti → Aggiungi prodotto**, inserire titolo e immagine in evidenza.
2. Compilare etichetta editoriale, breve descrizione ed eventuale racconto nel box Scheda prodotto.
3. Aggiungere una gallery facoltativa dalla libreria Media.
4. Assegnare Categorie, Occasioni e Idee regalo dai rispettivi pannelli.
5. Attivare “Mostra tra le Novità” o “Mostra in evidenza” solo per i prodotti selezionati. Entrambi sono spenti per default.

I termini si creano da Prodotti → Categorie, Occasioni o Idee regalo. Nessun nome di occasione o idea regalo è predefinito.

Per un’Occasione, l’icona è scelta dal set controllato. Si possono aggiungere immagine, titolo e introduzione editoriali. Per renderla attiva nelle future query Home, impostare entrambe le date in formato calendario; l’intervallo è inclusivo e valutato nel timezone configurato in WordPress. Date mancanti, non valide o invertite non attivano il termine, ma non ne nascondono archivio e prodotti associati. Per le Idee regalo si può scegliere un’icona dallo stesso set.

Per creare una raccolta editoriale Idea regalo:

1. Aprire **Prodotti → Idee regalo → Aggiungi nuova idea regalo** e inserire nome e, se utile, slug.
2. Scegliere un’icona dal set controllato.
3. Selezionare un’immagine dalla Media Library; è possibile sostituirla o rimuovere solo l’associazione senza cancellare il file.
4. Inserire titolo editoriale opzionale, breve introduzione e descrizione estesa. La descrizione consente markup filtrato e sicuro.
5. Salvare il termine e assegnarlo a uno o più Prodotti dal relativo pannello **Idee regalo**.
6. Per modificarla tornare a **Prodotti → Idee regalo**. Per togliere un’Idea da un Prodotto, modificare quel Prodotto e deselezionare il termine: non si crea una relazione separata.

Le Idee regalo non hanno date né stati automatici: sono raccolte permanenti con una futura pagina pubblica della tassonomia. Il titolo editoriale, se presente, sarà usato al posto del nome nella presentazione; altrimenti vale il nome del termine.

## Verifiche manuali in Local

- creare un prodotto e verificare titolo, excerpt, editor del racconto, immagine e gallery al salvataggio/riapertura;
- verificare Categorie, Occasioni e Idee regalo nei menu e sui prodotti;
- creare un’occasione, impostare le date comprendenti oggi e controllare `sarafatto_is_occasion_active()`; provare un periodo futuro/passato, date mancanti, una data impossibile e un intervallo invertito;
- provare selezione icona e anteprima sulle schermate di creazione e modifica, sia per Occasione sia per Idea regalo;
- lasciare entrambi i flag prodotto disattivati e verificare `sarafatto_get_product_flags()`; poi attivarli separatamente e verificare l’indipendenza;
- controllare che utenti autorizzati possano gestire termini e prodotti;
- salvare Impostazioni → Permalink una volta in Local per aggiornare le rewrite rules di `/prodotti/` e tassonomie.
- dopo l’installazione Polylang, verificare le traduzioni collegate IT/EN di pagine, prodotti e tassonomie; controllare che le traduzioni prodotto usino i termini tradotti;
- cambiare i flag Novità/In evidenza e le date/icone strutturali e controllare la copia/sincronizzazione tra traduzioni;
- verificare che immagini e gallery vengano copiate alla creazione ma possano poi differire, e che testi editoriali restino modificabili separatamente;
- testare lo switcher su una pagina, prodotto e termine con e senza traduzione disponibile; l’alternativa senza traduzione non deve puntare alla Home;
- disattivare Polylang in ambiente di prova e verificare che helper/sito non generino fatal error e lo switcher scompaia.

Il database di questo ambiente non è stato ispezionabile via WP-CLI o client MySQL. Prima di adottare il modello su contenuti legacy, verificare se esistono post `sarafatto_novita` o `sarafatto_selezione`: i record non sono cancellati, ma i vecchi tipi non vengono registrati e possono sparire dall’admin finché non si convertono o ripristinano temporaneamente. Pianificare l’esportazione/conversione manuale prima dell’uso su dati reali.

## Asset del tema

Da `themes/sarafatto`:

```sh
npm install
npm run dev
npm run build
```

La build riguarda il frontend del tema; non è richiesta per le modifiche admin del plugin. Non versionare `node_modules`, `hot`, output generato o credenziali.

I font self-hosted attesi sono `assets/fonts/fraunces/fraunces-variable.woff2` e `assets/fonts/manrope/manrope-variable.woff2`. I file non sono inclusi: aggiungerli prima della build di produzione per eliminare il fallback. `@font-face` usa `font-display: swap`; non sono previsti font esterni o preload. CSS e JavaScript sorgenti sono in `assets/src/css/app.css` e `assets/src/js/`; la pipeline Vite esistente genera `assets/dist`.

## Verifiche del tema

Da `themes/sarafatto`, usare `npm run build`; per i PHP eseguire `php -l` sui file modificati e dalla root `git diff --check`. Verificare in Local menu e switcher su IT/EN, pannello mobile a 320/375px, tastiera/Tab, Shift+Tab, Escape, ritorno del focus, scroll body, footer con e senza contatti/social/menu e assenza di overflow fino a 1920px. L’editor deve mostrare la sola palette, famiglie e scala predefinite del tema.
