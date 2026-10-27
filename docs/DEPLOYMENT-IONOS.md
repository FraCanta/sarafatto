# Anteprima rilascio IONOS

Questa fase prepara e confronta una release, ma non pubblica file. Il workflow esegue validazione e build su `push` a `main`; `workflow_dispatch` resta disponibile per i dry-run e l'ispezione opzionale. Nessun trigger esegue una pubblicazione.

## Percorsi e protezioni

Il pacchetto comprende `themes/sarafatto/`, `plugins/sarafatto-core/` e il solo `mu-plugins/sarafatto-polylang-front-page-url.php`. Viene creato da `git archive` sul commit autorizzato, quindi non include modifiche locali non committate, `uploads`, plugin o temi non allowlisted, configurazioni o file `.env`. La build Vite sostituisce soltanto `themes/sarafatto/assets/dist` nell'artefatto temporaneo.

Sul server vengono letti esclusivamente `/home/www/public/wp-content/themes/sarafatto`, `plugins/sarafatto-core` e il singolo MU plugin elencato. La sola esclusione interna al tema è `themes/sarafatto/node_modules/`: è una directory di dipendenze di sviluppo npm, non inclusa in `git archive` e non necessaria alla build distribuita. L'inventario ne riporta soltanto i conteggi di file e symlink; il confronto SHA-256, il controllo bloccante dei symlink e `rsync` non la attraversano. Il validatore rifiuta l'artefatto se `node_modules` compare nel pacchetto. Non vengono escluse altre directory per nome: cache o contenuti aggiuntivi nell'allowlist restano visibili nel confronto e vanno classificati, mai eliminati automaticamente.

Lo script acquisisce hash e inventario; tre invocazioni `rsync` usano sempre `--dry-run`, senza `--delete`. Il report riassume i contenuti extra sul server e ne dettaglia al massimo 20 per categoria; vecchi bundle Vite e backup sono esplicitamente segnalati come conservati. Non viene eseguito `git pull`, né alcuna scrittura in `/home/www/public`.

## Configurazione repository GitHub

Impostare queste **Actions Variables**:

- `IONOS_SSH_HOST`: `access-5021716180.webspace-host.com`
- `IONOS_SSH_USER`: `su1667607`
- `IONOS_SSH_PORT`: porta SSH dell'account da confermare nelle impostazioni IONOS

Impostare questi **Actions Secrets**:

- `IONOS_SSH_PRIVATE_KEY`: contenuto della chiave privata dedicata; non inserirla nel repository o nei log.
- `IONOS_SSH_KNOWN_HOSTS`: righe `known_hosts` per host e porta, con fingerprint verificata tramite un canale indipendente.

La chiave privata non è letta o generata da questo workflow. Poiché SSH usa `BatchMode=yes`, la chiave deve essere utilizzabile senza prompt interattivi; una chiave protetta da passphrase fallisce in modo chiuso. Per una porta non standard, la riga `known_hosts` deve usare la forma `[host]:porta`. Il server deve avere `ssh`, `rsync`, `realpath`, `find`, `sha256sum`, `stat` e Bash. È stato riferito che IONOS dispone di rsync 3.2.7; verificare la disponibilità nell'account che eseguirà l'operazione.

## Avvio e interpretazione

Da Actions avviare **IONOS deployment preview** sul branch `main` e inserire lo SHA completo del commit selezionato. Il workflow si arresta se branch, SHA o build non coincidono, se il manifest o un asset manca, se l'artefatto esce dall'allowlist, se vi sono symlink nei percorsi gestiti (escluso soltanto `themes/sarafatto/node_modules/`) o se SSH/rsync fallisce. La validazione esegue fixture locali su runner Ubuntu per verificare l'esclusione npm, il blocco di un symlink gestito, la classificazione degli hash e la conservazione degli extra.

Il riepilogo del job riporta conteggi e dettagli limitati di file nuovi, modificati, invariati e presenti soltanto in produzione (mai eliminati), conteggi sintetici di `node_modules`, drift dalla baseline e righe `rsync --dry-run`. In assenza di `/home/www/sarafatto-deploy/state/production-inventory.tsv` non è possibile verificare l'assenza di modifiche manuali o distinguere tali modifiche da divergenze di release. Questa fase non crea tale baseline.

## Seguito del progetto

Prima di abilitare qualsiasi pubblicazione servono una baseline approvata, backup con verifica e retention, protezione GitHub Environment con approvazione, pubblicazione atomica/ordinata di tema e plugin, controlli HTTP, verifica hash post-pubblicazione e una procedura di rollback provata. Queste capacità non fanno parte di questa anteprima.

## Fase 3B — ambiente privato e bootstrap della baseline

Questa fase aggiunge strumenti locali, ma il workflow non li esegue via SSH e non contiene un job che scriva la baseline. Non effettuare ancora git pull su IONOS: le nuove utility devono prima essere revisionate e rese disponibili al comando remoto con una procedura approvata.

### Inizializzazione dell'area privata

La root prevista è /home/www/sarafatto-deploy, fuori da /home/www/public. Contiene state/, backups/, staging/, releases/, locks/ e logs/; root e directory hanno permessi 700, marker 600. Lo script scripts/deploy/init-private-environment.sh non accetta percorsi arbitrari e controlla la disponibilità di realpath, stat, id, find e delle utility di base prima di procedere:

~~~bash
bash /home/www/sarafatto-repo/scripts/deploy/init-private-environment.sh
~~~

Senza argomenti effettua una simulazione read-only. Solo dopo aver letto l'output ed esplicitamente autorizzato la creazione, il comando previsto è:

~~~bash
bash /home/www/sarafatto-repo/scripts/deploy/init-private-environment.sh --create
~~~

La modalità --create opera solo sulla root privata fissa; rifiuta symlink, proprietari inattesi, marker non riconosciuti e contenuti top-level estranei. Non tocca la directory pubblica. Non eseguire questi comandi come parte del test locale/GitHub.

### Inventario remoto e confronto

scripts/deploy/baseline-inventory.sh legge esclusivamente i tre componenti autorizzati. Emette record FILE con SHA-256, dimensione, permessi e percorso relativo, record SYMLINK con destinazione testuale, un record sintetico per themes/sarafatto/node_modules/ e il terminatore END. Non attraversa symlink; se una raccolta è incompleta, il terminatore manca e il confronto fallisce. Richiede inoltre realpath, find, sha256sum, stat, wc, cut e readlink.

L'inventario va acquisito con il futuro job read-only, salvando lo stdout sul runner GitHub e non su /home/www/public. Il confronto previsto è:

~~~bash
python3 scripts/deploy/baseline_tool.py compare \
  --artifact-inventory "$RUNNER_TEMP/sarafatto-inventory.tsv" \
  --remote-inventory "$RUNNER_TEMP/sarafatto-public-inventory.tsv" \
  --release-sha "$GITHUB_SHA" \
  --authorized-sha "$GITHUB_SHA" \
  --release-id "bootstrap-$GITHUB_SHA" \
  --run-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID" \
  --accept-extra 'themes/sarafatto/assets/dist/assets/OLD_HASHED_FILE.js' \
  --accept-extra 'themes/sarafatto/KNOWN_BACKUP.php.bak' \
  --candidate-out "$RUNNER_TEMP/baseline-candidate.json"
~~~

Gli esempi OLD_HASHED_FILE.js e KNOWN_BACKUP.php.bak sono segnaposto, non percorsi da accettare alla cieca. Ogni extra deve essere letto nel report e approvato per percorso specifico. Il confronto blocca su SHA o dimensioni differenti, file mancanti, symlink gestiti, inventari malformati/incompleti, SHA autorizzato non coincidente e file extra non approvati. Un extra approvato viene registrato con hash, dimensione, permessi e classificazione, ma mai eliminato. Il report limita i dettagli per categoria; node_modules compare soltanto come conteggio.

### Schema baseline e inizializzazione

Il candidato JSON usa schema_version: 1, SHA commit completo, release ID, URL della run, provenienza bootstrap-content-match, timestamp verified_at_utc, hash dell'inventario remoto, file gestiti con SHA-256/dimensione/permessi, extra accettati, esclusioni e stato verified-awaiting-initialization. publication_date è null: la corrispondenza dei contenuti non dimostra quando né tramite quale processo siano stati pubblicati.

La preparazione del candidato è una verifica read-only; la sua approvazione consiste nella revisione e conservazione del relativo SHA-256. L'inizializzazione è separata e non accetta alcun file di inventario remoto: sotto un `flock` esclusivo nella directory privata, verifica che `scripts/deploy/baseline-inventory.sh` nel repository IONOS coincida byte per byte con il blob dello SHA autorizzato e passa a Bash proprio quei byte verificati. Lo script usa la root pubblica fissa e non accetta argomenti in modalità server. Confronta una prima fotografia con l'artefatto e il candidato approvato, poi acquisisce una seconda fotografia immediatamente prima della scrittura. Entrambe devono concordare su hash, dimensioni, permessi, file gestiti, extra classificati, esclusioni e SHA autorizzato. Non è possibile usare l'inventario salvato durante la preparazione come fotografia finale.

Esempio indicativo, da eseguire solo in una successiva fase approvata sull'ambiente che contiene la root privata:

~~~bash
python3 /percorso-approvato/baseline_tool.py initialize \
  --candidate /percorso-privato/baseline-candidate.json \
  --artifact-inventory /percorso-privato/artifact-inventory.tsv \
  --authorized-sha 'SHA_COMPLETO' \
  --approved-candidate-sha256 'SHA256_DEL_CANDIDATO_REVISIONATO' \
  --confirm-initial-baseline 'INITIALIZE SHA_COMPLETO'
~~~

Il comando rifiuta baseline esistenti, mantiene il lock durante le due acquisizioni e la scrittura, crea un temporaneo privato con permessi restrittivi, ne verifica SHA-256 e JSON e infine effettua il rename atomico in `/home/www/sarafatto-deploy/state/baseline.json`. Il lock coordina soltanto le operazioni della pipeline che lo rispettano; non impedisce modifiche manuali o altri processi esterni. Le due fotografie riducono la finestra di race, ma non garantiscono atomicità assoluta rispetto a modifiche esterne non coordinate. Se l'acquisizione fallisce o una qualsiasi differenza viene rilevata, la baseline non viene scritta. Il workflow attuale non invoca l'inizializzazione. Non usare `/percorso-approvato` come comando letterale: il file deve essere reso disponibile a uno SHA revisionato, senza git pull automatico sul server.

### Bootstrap senza deploy

Per adottare un sito già allineato non serve pubblicare nuovamente i 160 file. Serve invece acquisire un inventario remoto aggiornato e confrontarlo byte per byte con l'artefatto del commit autorizzato. Solo se tutti i file dell'artefatto corrispondono, non ci sono file mancanti/conflitti/symlink e gli extra (inclusi i vecchi bundle e i backup) sono stati esaminati e approvati, si può generare un candidato. L'inizializzazione privata successiva registra l'equivalenza dei contenuti allo SHA, non una data storica di deploy. Se baseline manca, non si può concludere che modifiche manuali storiche non siano mai avvenute; eventuali differenze bloccano l'adozione.

### Test e primo test GitHub

scripts/deploy/test_baseline_tool.py copre il confronto e l'inizializzazione su fixture locali, inclusi cambiamenti successivi al candidato (contenuto, file mancante, extra, symlink e permessi), inventario obsoleto non accettato, script inventario non corrispondente al commit, lock occupato, baseline già esistente e fallimento dell'acquisizione. scripts/deploy/test-baseline-inventory-fixture.sh prova l'inventario effettivo con symlink npm e symlink gestito. Il job `validate` esegue test e fixture senza Secrets o SSH; imposta `SARAFATTO_REQUIRE_FLOCK=1`, perciò fallisce se `flock` manca o se un test risulta saltato.

Per il primo test GitHub: selezionare main e lo SHA completo; lasciare run_remote_dry_run disattivato. Si eseguono validate e build-artifact, non si acquisisce inventario remoto e non si scrive alcuna baseline. La verifica remota read-only e l'eventuale inizializzazione privata richiederanno un job o una procedura separata, da approvare prima dell'implementazione. Nessun job di deploy è previsto in questa fase.

## Fase 3C — backup applicativo verificato e restore-test

Questa fase aggiunge strumenti locali per la futura esecuzione controllata su IONOS. Il workflow GitHub esegue soltanto sintassi e fixture locali: non invoca i comandi `backup`, `verify` o `restore-test`, non usa Secrets per questi test, non crea backup remoti e non ripristina file pubblici. Non è implementato un restore reale.

### Perimetro e preflight

Il backup legge soltanto `themes/sarafatto/`, `plugins/sarafatto-core/` e il MU plugin `mu-plugins/sarafatto-polylang-front-page-url.php`, includendo i file extra registrati nella baseline. L'unica esclusione è `themes/sarafatto/node_modules/`. Un file nuovo non presente nella baseline, un file mancante o una differenza di hash, dimensione o permessi blocca l'operazione. I symlink nei percorsi gestiti bloccano sempre. Il tool verifica marker, proprietario e permessi dell'area privata e SHA-256/schema della baseline.

Backup, verifica e simulazione usano il lock POSIX esclusivo persistente `/home/www/sarafatto-deploy/locks/site-operation.lock`; l'inizializzazione baseline usa lo stesso file e le future operazioni di deploy dovranno acquisire lo stesso lock. Per backup e restore-test le directory `state`, `locks`, `backups` e `staging` vengono aperte con descriptor POSIX (`O_DIRECTORY|O_NOFOLLOW`); creazione, scrittura dei manifest, estrazione e finalizzazione operano relativamente ai descriptor, verificando anche che i nomi siano ancora associati agli inode aperti. Una sostituzione con symlink rilevata ai punti di controllo blocca l'operazione e non reindirizza le scritture al target del link.

Limite residuo: un processo concorrente con lo stesso UID può rinominare una directory privata già aperta fuori dalla root mentre il processo la usa. I descriptor continuerebbero a riferirsi allo stesso inode; nessuna primitiva POSIX usata qui impedisce a un altro processo dello stesso account di rinominarlo. I controlli rilevano le sostituzioni osservabili, ma non chiudono atomicamente questa finestra contro processi non cooperanti dello stesso UID. Il lock coordina solo gli strumenti che seguono il protocollo. Prima dell'uso operativo, evitare processi concorrenti non coordinati e verificare l'account e i permessi effettivi IONOS.

Il sistema calcola lo spazio su disco con `statvfs`/`shutil.disk_usage`, ma questo non rivela necessariamente la quota effettiva Ceph/IONOS. Prima di ogni backup occorre controllare manualmente la quota residua nell'account IONOS e fornire al comando il valore in byte verificato. Il preflight richiede almeno due volte la dimensione dei file più un margine del 5% (minimo 16 MiB), per coprire archivio, restore-test e margine operativo. Un valore non disponibile o insufficiente blocca il backup. Non equivale a una lettura automatica della quota: va verificato con accuratezza e aggiornato al momento dell'operazione.

### Formato e finalizzazione

Ogni snapshot ha un ID UTC univoco e viene preparato in `/home/www/sarafatto-deploy/backups/.incomplete-<id>-<nonce>/`. Il formato contiene `payload.tar.gz` con i file ai percorsi relativi originari, `manifest.json`, `manifest.sha256` e infine `COMPLETE`. Il manifest include versione schema, ID e timestamp UTC, commit e SHA della baseline, perimetro/esclusione, elenco file con SHA-256, dimensione, permessi e classificazione, oltre a dimensione e SHA-256 dell'archivio. Il marker `COMPLETE` lega lo snapshot al digest del manifest.

Il TAR viene verificato prima della finalizzazione: solo file regolari, percorsi allowlistati, niente symlink o file speciali, nessun duplicato, e corrispondenza di contenuti e permessi. Archivio, manifest e marker sono creati con `openat`/`O_EXCL|O_NOFOLLOW` relativi al descriptor della directory temporanea. Il backup temporaneo riceve `COMPLETE` soltanto dopo la verifica. Per la pubblicazione no-clobber usa `renameat2(RENAME_NOREPLACE)` quando supportato; per gli errori di non supporto ammessi usa la finalizzazione privata verificata `mkdirat` + copie `O_EXCL` ancorate a descriptor, pubblicando `COMPLETE` per ultimo. Gli altri errori restano bloccanti. Directory `.incomplete-*`, file temporanei e vecchi backup non vengono cancellati automaticamente.

Il digest del manifest stampato alla creazione va conservato indipendentemente dal backup. I comandi `verify` e `restore-test` richiedono quel digest e lo confrontano, oltre a ricontrollare la baseline, il manifest, l'archivio e ogni membro. I digest interni rilevano corruzioni; la copia indipendente del digest permette di rilevare anche la sostituzione coordinata di archivio e manifest nella directory privata.

### Comandi operativi (da eseguire solo dopo l'approvazione)

Elenco read-only: distingue directory incomplete/anomale da backup autoconsistenti. Per dichiarare verificato un backup occorre anche il comando `verify` con digest del manifest conservato indipendentemente:

~~~bash
python3 /home/www/sarafatto-repo/scripts/deploy/backup_tool.py list
~~~

Creazione: il valore seguente è la quota libera **verificata manualmente**, espressa in byte. Il comando stampa un ID e il digest del manifest; registrare entrambi:

~~~bash
python3 /home/www/sarafatto-repo/scripts/deploy/backup_tool.py backup \
  --baseline-sha256 '07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd' \
  --account-quota-free-bytes 'BYTE_QUOTA_CONFERMATA'
~~~

Verifica read-only di un backup specifico; sostituire ID e digest con i valori restituiti alla creazione:

~~~bash
python3 /home/www/sarafatto-repo/scripts/deploy/backup_tool.py verify \
  --backup-id 'ID_BACKUP' \
  --baseline-sha256 '07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd' \
  --manifest-sha256 'SHA256_MANIFEST_REGISTRATO'
~~~

Restore-test: crea una nuova directory privata sotto `staging/`, verifica prima il backup e poi i file estratti. Non accetta una destinazione fornita dall'operatore, non scrive nella webroot e non rimuove prove precedenti:

~~~bash
python3 /home/www/sarafatto-repo/scripts/deploy/backup_tool.py restore-test \
  --backup-id 'ID_BACKUP' \
  --baseline-sha256 '07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd' \
  --manifest-sha256 'SHA256_MANIFEST_REGISTRATO' \
  --account-quota-free-bytes 'BYTE_QUOTA_CONFERMATA'
~~~

Un backup valido contiene tutti e quattro gli elementi previsti e passa `verify`. Un `.incomplete-*`, un `COMPLETE` assente, un checksum mancante, un TAR troncato o qualsiasi anomalia risultano incompleti/invalidi e non sono selezionabili dal restore-test. Non correggere o cancellare automaticamente tali directory: conservarle per l'analisi e decidere manualmente come procedere.

### Limiti

Questi sono backup dei soli componenti applicativi del progetto; non includono database, `uploads`, `wp-config.php`, plugin di terze parti o temi esterni e non sostituiscono un backup WordPress completo. `restore-test` dimostra che lo snapshot è leggibile e riproducibile in staging; non implementa il ripristino in produzione né attesta da solo la recuperabilità dell'intero sito. Non vengono eliminati backup vecchi e non viene usato `rsync --delete`.

I test in `scripts/deploy/test_backup_tool.py` coprono anche otto bundle Vite precedenti e `home-hero.php.bak`: tutti e nove sono acquisiti dal contenuto della baseline, verificati nel manifest/archivio e recuperati nel restore-test; modifica o assenza di ciascun extra blocca il backup. Altri test sostituiscono `backups` e `staging` con symlink dopo l'apertura dei descriptor e verificano il fallimento chiuso senza scritture nel target. Le fixture Bash si eseguono nel job `validate` su Ubuntu. Con `SARAFATTO_REQUIRE_FLOCK=1`, CI fallisce se `flock` non è disponibile o se un test viene saltato. I test usano esclusivamente directory temporanee locali e non accedono a IONOS.

## Fase 3D.1 — Registro dello stato corrente

La baseline `state/baseline.json` resta immutabile e descrive l'adozione iniziale verificata. `release_state_tool.py` introduce lo schema versionato `state/current-release.json`: contiene il commit iniziale verificato, release ID, digest dell'inventario del perimetro gestito, digest della baseline, snapshot dei file di riferimento, provenienza, verifica e campi separati per candidata, backup pre-deploy, operazione attiva e ultima operazione conclusa. Il digest dell'inventario esclude i conteggi di `node_modules`, che resta fuori dal perimetro gestito. Il digest interno del documento rileva corruzioni accidentali; non è una firma contro un amministratore con accesso alla root privata.

Il bootstrap è una tantum e richiede la baseline già inizializzata. Sotto lo stesso `site-operation.lock`, verifica baseline e permessi, acquisisce due inventari freschi con lo script inventario verificato contro il commit contenuto nella baseline, rifiuta differenze, symlink e journal irrisolti, quindi crea il nuovo file esclusivamente in `state/`. La pubblicazione usa file temporaneo, `fsync`, hard link no-clobber e sincronizzazione della directory. Non sovrascrive uno stato esistente e non scrive in WordPress pubblico. Il comando previsto, **non eseguito** in questa fase, richiede conferma esplicita del digest:

~~~bash
python3 /home/www/sarafatto-repo/scripts/deploy/release_state_tool.py bootstrap \
  --confirm-bootstrap 'INITIALIZE-CURRENT 07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd'
~~~

Il journal privato `state/operation-journal.jsonl` usa eventi con hash concatenati e transizioni validate, scritti sotto `site-operation.lock`. Symlink, hard link, file vuoti, record incompleti, ID intercalati e stati malformati bloccano la lettura. `committed` viene rifiutato anche se un record presenta una catena di digest formalmente valida: in questa fase non esiste un verificatore di deploy. Una transazione incompleta o `recovery_required` blocca bootstrap, creazione backup e restore-test; `verify` e `list` restano disponibili come controlli diagnostici read-only.

`backup_tool.py backup` continua ad accettare il digest della baseline originale come ancora immutabile. Se `current-release.json` non esiste, crea il formato storico legato alla baseline; se esiste, deve superarne schema, digest e relazione con la baseline e usa il relativo snapshot di file come riferimento, senza accettare SHA o release arbitrari dalla CLI. In Fase 3D.1 lo stato consumabile dal backup è limitato al bootstrap iniziale e deve coincidere esattamente con i file della baseline; qualsiasi stato di release successivo resta bloccato finché una fase futura non implementerà il verificatore di transazione. I nuovi manifest conservano sia il riferimento alla baseline originale sia l'identità/digest dello stato corrente. `verify` e `restore-test` mantengono la verifica dei manifest Fase 3C privi del campo `reference_state`; anche i nuovi manifest sono verificati contro digest, inventario registrato e archivio. I backup verificati già esistenti non vengono riscritti.

Il repository locale non contiene il payload/manifest privato del backup IONOS `20261024T181841Z-bdcc8d63457a`; la compatibilità di quel singolo archivio non è quindi verificabile offline. Il percorso di verifica legacy resta invariato: manifesta senza `reference_state`, digest esterno del manifest, SHA baseline, file manifestati e contenuto TAR devono corrispondere.

Il job `validate` include fixture offline per bootstrap, errori, stato/journal e compatibilità dei backup. Su Ubuntu i test POSIX devono passare senza skip grazie a `SARAFATTO_REQUIRE_FLOCK=1`. Questa modifica non abilita deploy o rollback: la futura promozione di una release richiederà una transazione verificata e un aggiornamento atomico dello stato, da progettare nella fase successiva.

## Fasi 3D.2 e 3D.3 — preflight e transazioni esclusivamente fixture

`transaction_fixture_tool.py` implementa preflight, piano JSON, backup fixture, pubblicazione simulata e rollback simulato. Non ha CLI e accetta esclusivamente un oggetto `FixtureWorkspace` creato sotto `tempfile.gettempdir()`, con marker e directory attese. Le radici applicative sono sempre derivate dal workspace; non è possibile passarle come argomento. `/home/www/public/wp-content`, symlink, traversal, file speciali e hard link sono rifiutati. Il modulo non importa né invoca SSH, rsync, WordPress o richieste HTTP.

Il preflight confronta commit autorizzato, inventario dell'artefatto e filesystem fixture con `current-release.json`; verifica il manifest Vite e tutti i suoi asset/import, identifica aggiunte, sostituzioni, invariati, rimozioni candidate ed extra approvati, calcola il digest del piano e stima backup/staging/margine di spazio. Il digest rende rilevabili modifiche accidentali, ma non sostituisce la verifica: prima di simulare la pubblicazione il piano viene ricostruito dal vivo e confrontato con stato, artefatto e azioni ricalcolate.

Le rimozioni sono soltanto elencate dal preflight. Per simularle occorre chiamare separatamente `approve_fixture_removals`, confermando il digest del piano e ogni percorso; la mappa di approvazione include lo SHA atteso. Ogni file è ricontrollato prima della rimozione. Extra approvati e `node_modules` non diventano candidati alla rimozione.

La simulazione acquisisce `site-operation.lock`, valida uno snapshot di backup fixture privato e copia l'artefatto in staging privata. Pubblica i singoli file soltanto nell'albero `workspace.public_root` interno alla root temporanea: nuove destinazioni usano link no-clobber; sostituzioni usano `renameat2(RENAME_EXCHANGE)` e verificano il file sostituito; se la primitiva manca l'operazione fallisce chiusa. Prima e dopo le scritture vengono ricontrollati gli hash, dimensioni e permessi. Non si assume atomicità dell'intera release: durante le sostituzioni per file può esistere una versione mista, che questo simulatore non dichiara sicura per una pubblicazione WordPress reale.

Il journal fixture usa lo stesso `operation-journal.jsonl`, schema hash-chain e validatore della Fase 3D.1. L'API normale continua a rifiutare `committed`; solo il verificatore interno del simulatore può registrarlo dopo aver riletto e confrontato tutti i file fixture e verificato il backup. Il parser accetta eventi committed marcati `fixture_only` soltanto quando è esplicitamente invocato dal motore fixture; il percorso normale del tool resta fail-closed. Gli errori dopo l'avvio della pubblicazione e i health check falliti/non disponibili lasciano l'operazione irrisolta o `recovery_required`, bloccando un nuovo preflight.

Il rollback fixture richiede ID transazione, backup ID, digest esterno e conferma esplicita. Verifica che l'albero simulato corrisponda alla transazione (o a uno stato parziale compatibile in recovery), conserva una copia privata dello stato corrente, prepara lo snapshot in staging e ripristina solo file verificati. Elimina dalla fixture file introdotti dalla release solo quando il loro hash coincide con il piano. Non copre il database e non può ripristinare né modificare file pubblici.

La salute è un input enum locale (`passed`, `failed`, `unavailable`), non un callback HTTP: `unavailable` e `failed` sono riportati distintamente dall'integrità dei file. Nessun test simula una risposta del sito come se fosse un health check reale. Fault injection copre arresto prima della prima scrittura, dopo scritture intermedie e prima del commit; sono inoltre previste prove per rollback, lock, collisioni, artefatti alterati, quota, symlink, hard link, file speciali, rimozioni non approvate e root pubblica vietata.

Il job `validate` esegue `test_transaction_fixture_tool.py` su Ubuntu con `SARAFATTO_REQUIRE_FLOCK=1`; qualunque skip POSIX fa fallire la suite. I test usano solo directory temporanee locali e non richiedono Secrets né SSH. La CI deve ancora confermare l'esecuzione Linux prima che il codice sia considerato validato.

Queste fasi non abilitano deploy o rollback reali, non modificano i file applicativi e non aggiornano `current-release.json`. Le simulazioni non garantiscono il corretto funzionamento di WordPress durante una pubblicazione reale. Prima di abilitare una futura modalità di produzione serviranno almeno: revisione indipendente del protocollo e delle race sul filesystem IONOS, verifica controllata delle primitive del filesystem, barriera di manutenzione o strategia verificata contro versioni miste, health check reale approvato, aggiornamento atomico dello stato corrente, backup applicativo e database separati, approvazione esplicita, recupero/rollback testato e workflow produzione isolato con permessi minimi. Nessuno di questi adattatori o job è incluso qui.

## Fase 3D.4 — ispezione remota protetta e blocco delle scritture pubbliche

`scripts/deploy/production_adapter.py` è un adattatore **solo read-only**. La CLI espone esclusivamente `inspect --authorized-sha <40 caratteri>`; non esistono sottocomandi bootstrap, publish, deploy o rollback. L'adattatore usa percorsi IONOS fissi, rifiuta componenti symlink, verifica che il repository remoto sia esattamente allo SHA autorizzato e che i sorgenti di controllo corrispondano ai blob Git. Verifica la baseline con lo SHA ufficiale, legge `current-release.json` e il journal senza seguire symlink, acquisisce un lock condiviso non bloccante e confronta due inventari pubblici freschi. Se lo stato corrente manca, restituisce `bootstrap-required` e termina con codice 3. Il report distingue la verifica dello stato corrente dalla readiness di pubblicazione: quest'ultima elenca esplicitamente barriera anti-versioni-miste, verificatore transazionale, backup fresco, health check e approvazione mancanti. Anche fornendo valori di prova a livello di test, il gate resta bloccato finché non esiste un publisher verificato. `publish_allowed` resta sempre `false`.

### Workflow manuale

Il workflow esegue build e validazione anche su push a `main`. `run_remote_state_inspection` è facoltativo, disattivato per default e attivabile solo da `workflow_dispatch`; se abilitato esegue solo `production_adapter.py inspect` via SSH, con chiave e host verificato, e non scrive sul server. Richiede che il repository IONOS sia stato aggiornato manualmente allo SHA del dispatch; altrimenti il controllo fallisce. Non avvia bootstrap, backup, staging o operazioni pubbliche. La build dell'artefatto e il job `remote-dry-run` restano separati.

### Runbook e classi di operazione

**Sola lettura** — da eseguire manualmente via SSH oppure con il dispatch read-only dopo aver verificato lo SHA:

~~~bash
cd /home/www/sarafatto-repo
GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/deploy/production_adapter.py inspect \
  --authorized-sha 'SHA_COMPLETO_DEL_COMMIT'
~~~

Il comando controlla baseline, repository, journal e filesystem. Non crea report su disco. Un `bootstrap-required`, una baseline diversa, un journal irrisolto, un lock occupato o differenze nei file impediscono di considerare lo stato verificato.

**Scritture solo nell'area privata** — il bootstrap dello stato corrente è separato e richiede autorizzazione esplicita. Non viene eseguito dal workflow né dall'adattatore:

~~~bash
python3 /home/www/sarafatto-repo/scripts/deploy/release_state_tool.py bootstrap \
  --confirm-bootstrap 'INITIALIZE-CURRENT 07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd'
~~~

Questo comando scrive esclusivamente `current-release.json` sotto `state/` e non modifica WordPress pubblico. Prima va acquisito e revisionato l'output di `inspect`; se la baseline o i due inventari non corrispondono, non procedere. Il comando già documentato `backup_tool.py backup` crea uno snapshot privato con lock esclusivo; verificarlo subito con `backup_tool.py verify`, conservando separatamente ID e digest del manifest. `restore-test` scrive solo sotto `staging/`. Questi comandi non sono invocati da questa integrazione GitHub.

**Scritture pubbliche** — non sono implementate né invocabili. Il workflow non contiene un job di deploy o rollback, non usa `rsync` per copiare file e non esegue cancellazioni. Non esiste ancora un verificatore che promuova `current-release.json` a una release successiva; la validazione dello stato corrente accetta solo il bootstrap iniziale.

### Gate obbligatori per un futuro workflow di pubblicazione

Prima di aggiungere un job reale dovranno essere implementati e testati insieme: SHA completo vincolato al ref `main`; artefatto scaricato e verificato byte per byte; Environment GitHub con revisori obbligatori configurati; preflight remoto e piano JSON il cui digest venga approvato; backup fresco verificato con ID e SHA indipendenti; acquisizione di `site-operation.lock` mantenuta per l'intera transazione; ricontrollo dell'inventario immediatamente prima e dopo le scritture; health check HTTP reale e controlli applicativi approvati; aggiornamento atomico e verificabile dello stato release; rollback vincolato a transazione, backup e digest; report con ogni file interessato. L'approvazione GitHub e la conferma del piano devono essere distinte dalla selezione dello SHA.

### Barriera contro versioni miste e compatibilità IONOS

Non è ancora dimostrabile che le richieste WordPress non possano osservare file appartenenti a release differenti. La sostituzione file per file consente uno stato misto durante la transazione; il lock applicativo non blocca le richieste web già in corso. Un flag `.maintenance` può fermare nuove richieste secondo il comportamento WordPress, ma non drena processi PHP avviati prima del flag e non prova la coerenza di OPcache o di tutti i worker. Uno switch atomico del solo symlink del tema non include plugin e MU-plugin; sostituire il symlink dell'intero `wp-content` rischierebbe di coinvolgere `uploads`, plugin/temi esterni e altri contenuti esclusi. Non adottare nessuna di queste ipotesi senza verifiche IONOS e un protocollo che copra tutti i componenti.

La compatibilità del filesystem IONOS non è confermata da test sul runner GitHub. I test esistenti coprono fallback e collisioni su filesystem di test, ma non dimostrano il comportamento del Ceph dell'hosting, le semantiche di rename/fsync, OPcache o la risoluzione dei symlink in PHP. Prima di autorizzare scritture servono prove circoscritte in area privata IONOS, senza percorsi pubblici, per le primitive usate; i risultati devono essere registrati e revisionati. Anche questo non autorizza da solo il deploy.

Fino alla soluzione della barriera contro le versioni miste, alla verifica controllata delle primitive IONOS e all'implementazione dei gate sopra, il deploy e il rollback reali restano bloccati. L'esito `verified-current` dell'ispezione registrato sul server è prova soltanto che inventario e stato corrente concordano in quel momento; non è un'autorizzazione né prova della sicurezza di una transazione. La Fase 4A e i relativi asset non fanno parte di questa pipeline.

## Banco privato per compatibilità filesystem e barriera release

`scripts/deploy/ionos_release_barrier_probe.py diagnose` crea un run univoco esclusivamente sotto `/home/www/sarafatto-deploy/staging/ionos-release-probe-<UTC>-<id>/`. Rifiuta path non canonici/symlink, richiede la directory staging posseduta dall'utente con permessi `0700`, usa descriptor e `O_NOFOLLOW` per aprire i componenti e non accetta path, destinazioni, `--force` o opzioni di cleanup. Non apre la webroot pubblica. Non cancella run precedenti; anche un run interrotto va ispezionato e classificato manualmente.

### Procedura IONOS

Prerequisiti: il commit contenente lo script deve essere stato installato nel repository IONOS con il normale processo di aggiornamento degli strumenti; questa procedura non lo fa. Prima, verificare separatamente che `/home/www/sarafatto-deploy/staging` esista già e abbia owner e modalità attesi. Eseguire manualmente:

~~~bash
cd /home/www/sarafatto-repo
GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/deploy/ionos_release_barrier_probe.py diagnose
~~~

Questo comando effettua scritture **solo nell'area privata staging**: crea directory e file fixture, prova symlink/`realpath`, rename di file e directory, modalità `0600`, `flock` esclusivo e `fsync` di file/directory. Se `php` CLI è disponibile raccoglie versione, SAPI, `open_basedir`, impostazioni OPcache/realpath e prova `include` di un file fixture privato. Produce `report.json` nella directory del run e stampa lo stesso report. Un errore può lasciare una directory di prova parziale, che non viene rimossa automaticamente.

La prova confronta quattro modelli artificiali: aggiornamento in-place, alias symlink separati per componente, singolo puntatore a una directory release e pagina di manutenzione durante una richiesta già attiva. Il singolo puntatore viene testato con thread Python che fissano il descriptor della directory release all'inizio della richiesta simulata; il modello **non** dimostra che PHP/WordPress fissino allo stesso modo i path, né che il cambio di symlink sia atomico per worker PHP-FPM o OPcache.

### Interpretazione e decisione

| Strategia | Esito richiesto nel probe/modello | Limite prima di adottarla |
| --- | --- | --- |
| In-place | Il modello deve rilevare uno stato misto | Conferma che il lock deploy non rende atomiche le richieste web. Non usarla senza barriera che dreni davvero i worker. |
| Quattro symlink, uno per componente | Il modello deve rilevare uno stato misto durante lo switch sequenziale | Rename atomico del singolo link non equivale ad attivazione atomica tema+plugin+MU-plugin+asset. |
| Un solo puntatore a release completa | Switch filesystem riuscito e zero richieste miste nella simulazione con directory descriptor fissato | È solo una candidata. Va provato che il bootstrap PHP risolva una release una volta per richiesta e che tutte le costanti/percorse WordPress usino quella radice, separando uploads e plugin terzi. Va verificata compatibilità IONOS dei symlink, rename e OPcache. |
| Manutenzione | Il modello deve mostrare che una richiesta già avviata può attraversare l'aggiornamento | Una pagina `.maintenance` non dimostra il drain delle richieste esistenti o l'invalidazione di tutti gli opcode. |

Un esito `false` per symlink, rename, `flock` o `fsync` blocca ogni strategia che dipenda da quella primitiva. `fsync` riuscito prova soltanto che la chiamata non ha restituito errore nell'area privata; non prova la durabilità dichiarata dal filesystem remoto. Il probe non altera baseline, stato, journal o backup.

### Verifiche ancora necessarie in ambiente isolato

I valori `open_basedir`, OPcache, `realpath_cache_*`, SAPI e `include` raccolti dal probe sono quelli di **PHP CLI**, non della configurazione web. Per dimostrare il comportamento reale serve un vhost/docroot PHP isolato, autorizzato e separato dalla webroot attiva, con due release artificiali e richieste HTTP concorrenti che restituiscano la quadrupla di versioni. Non pubblicare script di test sotto `/home/www/public`, non usare il database WordPress e non usare il sito live come banco prova. Se IONOS non offre un ambiente HTTP/PHP-FPM isolato equivalente o non consente di verificare OPcache e il pin della release per richiesta, la compatibilità delle richieste reali resta **non dimostrata** e il deploy deve rimanere bloccato.

Il workflow esegue build e validazione su push a `main` e conserva `workflow_dispatch` per le operazioni manuali. L'aggiunta dei test offline del probe al job `validate` non introduce job SSH, backup remoto, deploy o rollback. Le fixture CI sono riproducibili su Ubuntu con:

~~~bash
SARAFATTO_REQUIRE_FLOCK=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/deploy/test_ionos_release_barrier_probe.py
~~~

Questa CI verifica il modello e le primitive POSIX del runner GitHub, non l'hosting IONOS. La prima pubblicazione potrà essere valutata solo dopo revisione dei report privati IONOS, collaudo HTTP/PHP-FPM isolato, prova documentata del pinning dei componenti per richiesta, gestione di OPcache, fault/recovery e rollback in un ambiente equivalente. Nessuno di questi risultati è presunto dal probe.

## Prova HTTP/PHP isolata A/B (senza WordPress)

IONOS documenta la creazione di sottodomini e il collegamento di un dominio a una directory del webspace, ma la possibilità di usare proprio il percorso privato `staging/` come document root e la sua accessibilità da Apache/PHP devono essere confermate nel contratto/account. La documentazione del pannello permette di identificare la document root; non dimostra che un percorso arbitrario fuori dall'albero web pubblico venga accettato. Verificare il target nel Domain Center prima di associare il sottodominio. Non selezionare `/home/www/public`, `wp-content`, la root WordPress o una directory che li contenga.

### Preparazione locale già inclusa nel repository

I file `scripts/deploy/http_php_release_probe.py` e `scripts/deploy/http-release-probe/{index.php,asset.php}` preparano un banco senza WordPress o database. Il comando `prepare` crea solo un run univoco sotto `staging/`, con `docroot`, due directory immutabili `release-A`/`release-B`, marker PHP per tema/plugin/MU-plugin, un asset per release e un puntatore iniziale `current -> release-A`. Il `.htpasswd` viene creato vuoto e `.htaccess` richiede Basic Auth: non associare il sottodominio finché l'autenticazione non è stata configurata e testata. I run precedenti non vengono cancellati.

Il front controller PHP chiama `realpath()` sul puntatore una volta all'inizio della richiesta, accetta soltanto la canonical path di A o B e usa poi quella radice immutabile per tutti e quattro i componenti. Il parametro di attesa è limitato a 0–2000 ms e viene applicato dopo la lettura del tema per mantenere richieste attive durante lo switch. L'endpoint asset accetta solo gli ID A/B. Entrambi restituiscono solo dati artificiali; nessun bootstrap WordPress, query o accesso al database.

### Prerequisiti manuali su IONOS

1. Eseguire i test filesystem privati della sezione precedente. Aggiornare manualmente il repository strumenti al commit che contiene il probe; non sovrascrivere o ripulire staging esistente.
2. Via SSH manuale autorizzata, eseguire `python3 scripts/deploy/http_php_release_probe.py prepare` e conservare l'ID e il percorso restituiti. Questo scrive solo in staging. Il comando non crea il sottodominio.
3. Verificare quale versione PHP il pannello assegna al sottodominio temporaneo e individuare il percorso CLI corrispondente al contratto. IONOS documenta percorsi CLI diversi secondo la data del contratto; non usare l'alias generico `php`. Eseguire `-l` sui due endpoint e su tutti i marker `release.php` dentro il run privato. Il PHP CLI può avere configurazione diversa dalla SAPI HTTP.
4. Configurare un utente Basic Auth nel `.htpasswd` privato usando `htpasswd` senza `-c` (il file è stato creato) se disponibile; non mettere la password nella command line o nel repository. Se l'utility manca, fermarsi e predisporre una generazione sicura del formato supportato. Verificare che `.htaccess` venga applicato: una richiesta anonima deve ricevere HTTP 401.
5. Solo dopo la protezione, creare manualmente un sottodominio temporaneo del tipo `release-probe-<id>.sara-fatto.it`, assegnargli la versione PHP scelta e tentare di collegarlo **esattamente** al `docroot` del run. Attivare HTTPS. Non installare WordPress, non associare il database e non aggiungere upload. Se IONOS rifiuta il percorso privato, richiede di spostarlo sotto la webroot pubblica, o impone di allargare i permessi di `/home/www/sarafatto-deploy` o `staging/`, fermarsi: questo banco non è isolato secondo i vincoli. Non allargare automaticamente i permessi.
6. Prima del carico, provare da una sessione anonima che HTTPS risponda 401. Verificare inoltre che path non valido non mostri file o listing e che PHP esegua il codice invece di scaricarlo come sorgente. Un esito diverso blocca la prova.
7. Dal server, avviare il test concorrente con l'host esatto del sottodominio:

~~~bash
cd /home/www/sarafatto-repo
GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/deploy/http_php_release_probe.py stress \
  --run-id 'ID_RESTITUITO_DA_PREPARE' \
  --host 'release-probe-ID.sara-fatto.it' \
  --requests 320 --workers 16 --hold-ms 500
~~~

Il tool accetta solo host `release-probe-*.sara-fatto.it`, TLS verificato, nessun redirect, controlla prima il 401 anonimo, chiede credenziali senza mostrarle e non le scrive nel report. Durante il carico cambia ripetutamente soltanto il symlink `releases/current` nel run privato, verifica JSON di ogni richiesta e recupera l'asset versione-specifico. L'ID run viene controllato con regex, marker, `.htaccess`, endpoint e hash/contenuto di tutte le fixture; symlink o file alterati bloccano il test. Il puntatore viene ripristinato al target iniziale in un `finally`; un kill non gestibile può lasciarlo su A o B, entrambi validi e privati. Report JSON salvato nel run privato. Non viene toccata alcuna directory del sito pubblico.

### Criteri di esito

Il report deve avere `status: passed`, tutte le richieste attese riuscite, zero combinazioni miste, zero errori HTTP/applicativi, almeno uno switch, risposte osservate sia da A sia da B e un solo profilo runtime coerente. Ogni risposta deve dichiarare versioni uguali per tema, plugin, MU-plugin e asset. Verificare manualmente che SAPI sia quella web (non CLI), PHP sia la versione assegnata al sottodominio, le impostazioni OPcache/realpath siano quelle attese e che non vi siano risposte cacheate. Confrontare almeno due run con valori diversi di `hold-ms` e concorrenza ridotta, oltre a un run ripetuto.

Una sola versione osservata, 401 assente, redirect, TLS/configurazione runtime variabile, 4xx/5xx, risposta non JSON, endpoint PHP scaricato, permessi insufficienti, symlink non supportati, `open_basedir` che blocca il run o qualsiasi mix implica `status: blocked`/arresto e nessuna conclusione di compatibilità. Non abbassare la protezione né esporre la webroot per far passare il test.

### Cosa prova e cosa non prova

Il test HTTP verifica l'esecuzione PHP sul sottodominio e che **questo front controller di prova** pinni la canonical path della release prima di caricare componenti artificiali. La directory release non viene modificata durante il test: cambiano solo il puntatore privato e le richieste leggono file immutabili. OPcache e realpath sono riportati per richiesta; percorsi A/B distinti evitano di mutare file già cacheati, ma non dimostrano il comportamento di WordPress né tutti i worker se il sottodominio usa pool diversi dal dominio principale. Non dimostra che WordPress possa caricare tema, plugin, MU-plugin e asset da una root comune senza modifiche/configurazione dedicate, né che `WP_CONTENT_DIR`, URL, uploads, plugin terzi o gli altri path siano preservati. Non prova un deploy o rollback reale.

Se il piano IONOS non consente document root privato, auth server-side, stessa versione/SAPI PHP, `open_basedir` adatto o un run HTTP isolato, il test va spostato su un webspace/contratto di test dedicato. Un account SFTP confinato alla directory non equivale a isolamento per gli script PHP; IONOS raccomanda un webspace/contratto distinto per la separazione effettiva. Anche con esito HTTP positivo, il deploy resta bloccato finché non si dimostra il bootstrap WordPress con root di release fissata per richiesta e non si collaudano fault, journal, backup, promozione stato e rollback in un ambiente equivalente.

## Barriera di coordinamento richieste PHP (opt-in, non è un publisher)

Il MU-plugin conserva il filtro Polylang esistente. La barriera è disattivata in assenza di una configurazione privata valida e `enabled: false`; inoltre il bootstrap opera solo con `WP_ENVIRONMENT_TYPE=production` e fuori dalla SAPI CLI. In questo stato un lock non accessibile non causa 503. La configurazione e il marker hanno percorsi fissi e non sono configurabili via richiesta. Il protocollo usa `locks/web-request.lock`: ogni richiesta web attiva acquisisce `flock(LOCK_SH|LOCK_NB)` e mantiene il descriptor fino allo shutdown PHP; una futura operazione dovrà armare prima il marker privato `state/request-deploy-window.json`, acquisire `LOCK_EX` sullo stesso inode con timeout finito e verificare il blocco HTTP prima di qualsiasi scrittura pubblica. Con marker presente, errori di configurazione o lock fanno rispondere 503 con `X-Sarafatto-Deploy-Barrier: active`; il marker non va rimosso automaticamente dopo un errore.

Il lock PHP è distinto da `site-operation.lock`: quest'ultimo coordina strumenti CLI, mentre `web-request.lock` coordina le richieste web. La disponibilità e i permessi del file per l'utente PHP sono prerequisiti da provare dalla SAPI web. Non allargare permessi automaticamente. La configurazione prevista è `0600`, così come il lock; se l'utente PHP non può accedervi, non attivare la barriera. Un errore senza marker lascia il sito nel comportamento preesistente e la verifica deve fallire; ciò non autorizza il publisher.

L'ordine lato richiesta è deliberato: controlla il marker prima di qualunque percorso normale; dopo aver acquisito `LOCK_SH`, ricontrolla il marker prima di proseguire. Se il marker è comparso fra i due controlli, rilascia subito il lock e risponde 503 anche se `flock` era riuscito. Se viene armato dopo il secondo controllo, la richiesta ha già il lock condiviso e il publisher deve attendere che termini. L'ordine lato publisher deve essere: creare il marker con `O_EXCL` e sincronizzarlo; acquisire `LOCK_EX` con timeout finito; verificare via HTTP l'interlock prima delle scritture. A operazione conclusa, rilasciare `LOCK_EX` e soltanto dopo rimuovere il marker. Rimuoverlo mentre si detiene ancora l'esclusivo lascerebbe una finestra in cui una richiesta vedrebbe marker assente ma non potrebbe acquisire `LOCK_SH`.

### Preparazione e verifica manuale

I comandi seguenti sono **solo istruzioni**, non sono stati eseguiti. Richiedono che gli strumenti siano già presenti nel checkout privato IONOS e che le directory private `state/` e `locks/` esistano con owner/modalità attesi.

1. **Scrittura solo nell'area privata:** `prepare-private` crea il lock se assente e una configurazione disabilitata, senza sovrascrivere file esistenti. Mostra una sola volta un token casuale: conservarlo in modo sicuro come Secret `SARAFATTO_BARRIER_STATUS_TOKEN`, senza inserirlo nel repository, nella command history o nei log.

~~~bash
cd /home/www/sarafatto-repo
PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/request_barrier_tool.py prepare-private
~~~

2. Configurare il Secret nel sistema approvato. Quindi verificare **via HTTPS e PHP web**, con configurazione ancora disabilitata. Questo effettua una GET autenticata all'endpoint read-only e salva una prova fresca solo nell'area privata.

~~~bash
SARAFATTO_BARRIER_STATUS_TOKEN='TOKEN_FORNITO_IN_MODO_SICURO' \
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/request_barrier_tool.py verify-http --phase accessibility
~~~

3. Solo dopo esito positivo della prova di accessibilità, `activate-private` cambia atomicamente `request-barrier.json` da disabilitato ad abilitato, esclusivamente nell'area privata. Non arma il marker e non scrive file WordPress pubblici.

~~~bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/request_barrier_tool.py activate-private
~~~

4. Verificare che richieste HTTP reali acquisiscano il lock condiviso e che lo stato attivo sia coerente. `assert-ready` ripete la verifica HTTP; **non** acquisisce lock esclusivo, non drena worker e non effettua pubblicazioni.

~~~bash
SARAFATTO_BARRIER_STATUS_TOKEN='TOKEN_FORNITO_IN_MODO_SICURO' \
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/request_barrier_tool.py verify-http --phase active
SARAFATTO_BARRIER_STATUS_TOKEN='TOKEN_FORNITO_IN_MODO_SICURO' \
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/request_barrier_tool.py assert-ready
~~~

Questi comandi non vanno copiati con il token in una shell che registra la history. Usare il secret store/runner autorizzato e un input mascherato; non stampare mai il token. `prepare-private`, `activate-private` e la scrittura delle prove toccano solo `state/` e `locks/` private. Le chiamate HTTP sono GET verso l'endpoint autenticato; non modificano contenuti WordPress.

### Prova del blocco e limiti

L'endpoint autenticato riporta SAPI/versione PHP, accessibilità/acquisizione del lock, hash sorgente/configurazione e impostazioni OPcache/realpath osservabili. Un test HTTP della richiesta attiva può usare `hold_ms` limitato (massimo 2 secondi) per mantenere `LOCK_SH`; il test dell'interlock esclusivo richiede invece un marker operativo armato e un processo che detenga `LOCK_EX`, dopodiché l'endpoint pubblico deve restituire 503 con l'header dedicato. Tale prova provoca indisponibilità intenzionale durante la finestra: eseguirla solo su un ambiente HTTP isolato o in una finestra esplicitamente autorizzata. Nessuna prova CLI dimostra che PHP-FPM condivida il medesimo inode/lock o che tutte le richieste siano terminate.

Un marker presente, anche invalido o non leggibile, è trattato conservativamente come finestra armata. In caso di interruzione il sito può continuare a rispondere 503 finché un operatore non verifica lo stato e rimuove il marker tramite una procedura di recovery autorizzata; non cancellarlo alla cieca. Se manca il Secret, l'endpoint non è raggiungibile, PHP non può leggere il lock o la prova è stantia, `assert-ready` fallisce e il publisher deve restare bloccato. Anche con esito positivo non esiste ancora un publisher reale: questo strumento non arma finestre operative e non scrive nel perimetro pubblico.

Prima di considerare la barriera operativa occorre verificare sul dominio la stessa SAPI/pool PHP, permessi effettivi, `open_basedir`, cache proxy/page cache, OPcache e realpath cache. Una cache che risponde senza eseguire WordPress può aggirare il MU-plugin; le richieste di file statici non sono bloccate. Una sostituzione atomica del solo file non richiede il drain per evitare sorgenti parziali: le richieste che hanno già aperto il vecchio inode terminano sul vecchio contenuto, quelle successive aprono il file nuovo. La cache realpath conserva la risoluzione del percorso, non una copia parziale del file. OPcache è diverso: worker diversi possono continuare temporaneamente a usare opcode vecchi o nuovi. Poiché la configurazione della barriera resta disabilitata durante questa migrazione e il codice Polylang è identico nelle due versioni, tale sovrapposizione non equivale a una release composta da file incompatibili; impedisce però di dichiarare la barriera attiva uniformemente. Prima di armarla serve un metodo IONOS verificabile per invalidare/riavviare il pool o attestare tutti i worker. La CI offline non dimostra questi comportamenti IONOS.

## Prima installazione pubblica della barriera MU-plugin — bloccata

La migrazione riguarda solo `mu-plugins/sarafatto-polylang-front-page-url.php`. Valori attesi fissati in `scripts/deploy/mu_plugin_migration_tool.py`: commit sorgente `50bbe01af38814f41d5a67bb37fef45b181f5fd1`, release pubblica precedente `911d6a72ac0f624dc85b43d53b1c299968d683f6`, inventario `d0aa002e885f252ddf23226eb59c30857dce4a1c24a03fc50da66aaadb1340cf`, baseline `07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd`, SHA vecchio MU-plugin `2ffd84b3f170ec2e0eae1cab5935391bb8e9d5311e3c55025719ab60d1417252` e SHA nuovo `1b4d430566abf2b01e3e22512212e2f03f623450e207366e63f02d97e85d4c7f`. Lo strumento non installa file: `PUBLIC_WRITE_ENABLED` è falso e `install` rifiuta sempre. Non esistono opzioni `force` o percorsi pubblici configurabili.

### Comandi read-only

Dopo aver reso disponibile il commit sorgente nel clone locale, verificare il blob autorizzato e il file candidato:

~~~bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/mu_plugin_migration_tool.py verify-local
PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/mu_plugin_migration_tool.py status
~~~

`verify-local` confronta il blob MU-plugin del commit autorizzato con il file locale; il `HEAD` degli strumenti può essere successivo. `status` mostra i blocchi e la conferma esatta richiesta. Sul server, solo dopo autorizzazione alle verifiche read-only, controllare commit, baseline, registro e inventario fresco con lo strumento esistente:

~~~bash
cd /home/www/sarafatto-repo
GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/deploy/production_adapter.py inspect \
  --authorized-sha '50bbe01af38814f41d5a67bb37fef45b181f5fd1'
~~~

Questi controlli non scrivono sul sito. `install --approve-operation 'INSTALL-MU-BARRIER …'` è deliberatamente bloccato e non va eseguito: neppure la conferma esatta abilita la scrittura.

### Verifica e attestazione separata del backup ufficiale

Il preflight usa il backup applicativo ufficiale `20261024T181841Z-bdcc8d63457a` con il digest manifesto indipendente noto `c502c1fe239515ff3324a4c55e77443c9a6ab7b8e6c77d4e3472a3d84ab369ae` e la baseline `07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd`. Non accetta percorsi o digest forniti al momento dell'esecuzione. Prima eseguire il comando read-only: verifica manifest, marker `COMPLETE`, archivio TAR, contenuti di tutti i membri e hash del MU-plugin senza creare attestazioni:

~~~bash
cd /home/www/sarafatto-repo
PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/mu_plugin_migration_tool.py verify-backup
~~~

Il comando acquisisce `site-operation.lock` e riusa `backup_tool.py`. Controlla che il record del MU-plugin abbia lo SHA della baseline e include nel report lo scope dei componenti gestiti: non copre database, uploads o plugin di terze parti. Per conservare il risultato verificato in una attestazione separata nell'area privata, eseguire poi `PYTHONDONTWRITEBYTECODE=1 python3 scripts/deploy/mu_plugin_migration_tool.py attest-backup`. Questa seconda operazione crea il file solo se assente e non sovrascrive il backup. Il backup dedicato manuale resta intatto e non viene usato come prova. L'attestazione non abilita `install`.

### Blocchi specifici della migrazione a file singolo

1. **Verifica server-side del backup:** il verificatore è vincolato all'ID ufficiale e al digest indipendente noto. La sua esecuzione read-only su IONOS resta necessaria per attestare che i byte presenti sul server corrispondano. Il backup dedicato manuale resta conservato, ma non è una prova sostitutiva.
2. **Journal e stato corrente:** è stata aggiunta una rappresentazione versionata e strettamente vincolata per il solo delta MU-plugin. Il commit della release applicativa resta quello della baseline (`911d6…`); il commit candidato è registrato separatamente come provenienza del componente. La baseline resta immutabile e il journal terminale deve concordare con il digest del nuovo current-release e dell'inventario. Il protocollo è implementato e testato solo sulle fixture locali; non esiste un comando di scrittura pubblica.
3. **OPcache e operatività della barriera:** un singolo endpoint HTTP non può attestare ogni worker. Dopo la sostituzione si può mantenere `request-barrier.json` disabilitato e il sito continua a ricevere richieste: vecchio e nuovo codice completo sono compatibili per il comportamento Polylang. Prima di abilitare la barriera, IONOS deve fornire un'azione verificabile di invalidazione/riavvio del pool PHP, oppure un meccanismo di attestazione che copra tutti i worker e le richieste instradate. Se nessuno dei due esiste, la barriera resta non attivabile e non si può iniziare il deploy multi-componente.
4. **Verifica applicativa:** eseguire lint PHP compatibile e controlli HTTP ripetuti di WordPress/Polylang, verificando hash live e versione del codice servita. La procedura di status attuale non effettua tali controlli.

### Sequenza prevista, senza drain per questa sola sostituzione

Il ripristino futuro del solo MU-plugin dovrà usare `payload.tar.gz` del backup ufficiale già verificato. Per preparare e controllare una copia **solo privata**, dopo `verify-backup`:

~~~bash
umask 077
archive=/home/www/sarafatto-deploy/backups/20261024T181841Z-bdcc8d63457a/payload.tar.gz
candidate=$(mktemp /home/www/sarafatto-deploy/staging/mu-plugin-restore.XXXXXX)
tar -xOzf "$archive" mu-plugins/sarafatto-polylang-front-page-url.php > "$candidate"
sha256sum "$candidate"
# Atteso: 2ffd84b3f170ec2e0eae1cab5935391bb8e9d5311e3c55025719ab60d1417252
~~~

Non estrarre il TAR nella webroot e non ripristinare gli altri membri. La copia candidata resta in staging privata; il writer che effettua lo swap atomico del solo pathname pubblico non è implementato né abilitato.

### Protocollo fixture della Fase 5

`mu_plugin_transaction_fixture_tool.py` fornisce API senza CLI, utilizzabili soltanto con un `FixtureWorkspace` creato e validato da `transaction_fixture_tool.py`. La fixture contiene un backup sintetico legato alla baseline di test e una prova ufficiale simulata con ID/digest fissati: non sostituisce l'esecuzione reale di `verify-backup` e non attesta il backup IONOS.

La simulazione segue la sequenza `prepared → backup_verified → publishing → files_verified → health_verified → component_migrated`. Il rollback usa una nuova operazione legata all'ID della migrazione e termina con `component_rolled_back`. Un arresto lascia il journal non terminale, che blocca le altre operazioni; `recover_migration()` riconcilia solo combinazioni verificate di journal, file e current-release. Un drift o un backup alterato viene rifiutato senza sovrascrivere il file inatteso. Le directory di staging orfane dopo un arresto prima del primo evento non vengono rimosse automaticamente.

`current-release.json` mantiene `release.commit_sha` e `release_id` della baseline e aggiunge `component_migration` per registrare esclusivamente target, hash precedente/nuovo, commit sorgente autorizzato, backup ufficiale, digest dello stato precedente e stato installato/ripristinato. `backup_tool.py` usa la fotografia corrente solo se il delta è esattamente quello autorizzato; `production_adapter.py inspect` confronta il live con tale fotografia e richiede il terminale journal corrispondente. Queste integrazioni sono soggette ai test CI e non autorizzano da sole scritture.

Test locali/CI:

~~~bash
SARAFATTO_REQUIRE_FLOCK=1 SARAFATTO_REQUIRE_POSIX=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 scripts/deploy/test_mu_plugin_transaction_fixture_tool.py
~~~

**Limite operativo:** `PUBLIC_WRITE_ENABLED` resta `False`; il sottocomando `install` continua a rifiutare ogni richiesta e non è stato aggiunto publisher o rollback IONOS. Il protocollo fixture non prova proprietà/permessi dell'utente PHP, semantica rename del filesystem remoto, OPcache, richieste PHP-FPM o health check live. Prima di qualunque attivazione futura servono revisione e collaudo separati, inclusa una gestione dimostrata dell'adozione OPcache; nessun comando operativo di migrazione è documentato o abilitato in questa fase.

Non occorre fermare richieste già avviate per proteggere l'integrità del singolo file. Occorre invece provare che il vecchio e il nuovo bytecode siano entrambi compatibili durante la finestra (il codice Polylang invariato e barriera disabilitata soddisfano la compatibilità osservabile dal diff) e non dichiarare la barriera attiva finché OPcache non sia uniformato. Questo non dimostra la sicurezza di una successiva pubblicazione di tema, plugin e MU-plugin insieme.
# Publisher IONOS: stato implementato e blocchi operativi

Il workflow ora valida e compila anche sui push a `main`. Questo **non pubblica**
su IONOS. Il trigger `workflow_dispatch` resta disponibile per dry-run e
ispezione read-only; nessun job di pubblicazione remota è attivo.

`scripts/deploy/production_publisher.py` è l'entrypoint di verifica della release.
La CI produce package, inventario, archivio `tar.gz` e provenance legati allo SHA
e al run GitHub; verifica inoltre che i byte dell'archivio corrispondano al
package, senza estrarre file. La provenance documenta il run e i digest, ma non
è una firma crittografica autonoma. Il comando `verify-artifact` esegue lo stesso
controllo offline. `preflight` confronta release, repository IONOS, stato
corrente e inventario live; accetta input soltanto sotto l'area privata
`/home/www/sarafatto-deploy/staging`. Il comando `backup` può creare un backup
fresco esclusivamente nell'area privata, con conferma esplicita e verifica
della quota. `publish`, `rollback` e `recover` sono ancora bloccati: current-release
e journal accettano al momento soltanto bootstrap iniziale e delta MU-plugin, e
gli strumenti backup rifiutano una release applicativa successiva. Non esiste
ancora un writer transazionale di produzione collaudato.

Comandi di sola lettura, da eseguire sul server solo durante il collaudo
autorizzato:

```sh
cd /home/www/sarafatto-repo
SHA='<40 caratteri esadecimali del commit autorizzato>'
python3 scripts/deploy/production_publisher.py status --authorized-sha "$SHA"
python3 scripts/deploy/production_publisher.py preflight \
  --release-sha "$SHA" \
  --package /home/www/sarafatto-deploy/staging/incoming/run-<run-id>-<sha12>/package \
  --inventory /home/www/sarafatto-deploy/staging/incoming/run-<run-id>-<sha12>/inventory.tsv \
  --provenance /home/www/sarafatto-deploy/staging/incoming/run-<run-id>-<sha12>/sarafatto-provenance.json \
  --archive /home/www/sarafatto-deploy/staging/incoming/run-<run-id>-<sha12>/sarafatto-release.tar.gz \
  --run-id '<ID del run GitHub verificato>'
```

`preflight` è read-only e richiede che i file siano già presenti nell'area
privata. Il workflow include il job manuale `stage-private-artifact`, attivabile
solo con l'input `stage_private_artifact=true`, la variabile repository
`IONOS_PRIVATE_STAGING_ENABLED=true`, i Secrets SSH e l'Environment GitHub
`ionos-private-staging`. Configurare l'Environment con revisori obbligatori prima
di valorizzare la variabile. Il job verifica la host key, prenota una directory
non riutilizzabile, trasferisce archivio/inventario/provenance via `scp` e lancia
`artifact_transfer_tool.py verify`. Il server verifica commit, run ID, digest,
contenuto e manifest, poi crea `TRANSFER_COMPLETE` per ultimo. Replay, file extra
e trasferimenti parziali bloccano la verifica; non avviene cleanup automatico.
La provenance non è una firma. Il job non esegue preflight, publish, rollback o
recovery e non scrive nella webroot.

Per il collaudo manuale, avviare il dispatch sulla stessa SHA di `main`, abilitare
solo `stage_private_artifact` e attendere l'approvazione dell'Environment. Il
package verificato sarà in
`/home/www/sarafatto-deploy/staging/incoming/run-<run-id>-<sha12>/package`;
inventario, archive e provenance restano nella stessa directory privata. Un run
incompleto non si riusa: va ispezionato e classificato manualmente, senza cleanup
automatico.

Creazione di un backup (scrive soltanto nell'area privata; non è un deploy):

```sh
python3 scripts/deploy/production_publisher.py backup \
  --account-quota-free-bytes 123456789 \
  --confirm 'CREATE-BACKUP 07f330549f9e889618dd9f00a346af0d841880594dc5f54ecdd9d3165486b6bd'
```

Sostituire `123456789` con la quota libera effettivamente verificata; non
eseguire il comando con il valore d'esempio.

I comandi seguenti sono intenzionalmente fail-closed e non costituiscono
procedure operative finché il writer non viene implementato, revisionato e
collaudato:

```sh
python3 scripts/deploy/production_publisher.py publish \
  --release-sha "$SHA" --package '<artefatto>' --inventory '<inventario>' \
  --provenance '<provenance>' --archive '<archivio>' --run-id '<run GitHub>'
python3 scripts/deploy/production_publisher.py rollback --operation-id '<id>' --backup-id '<id>' --manifest-sha256 '<digest>'
python3 scripts/deploy/production_publisher.py recover --operation-id '<id>'
```

Non impostare gate o Secrets per tentare di attivare la pubblicazione: il
workflow non contiene un job di scrittura pubblica e il CLI rifiuta `publish`,
`rollback` e `recover`. Il job di staging scrive esclusivamente sotto la root
privata dedicata. Prima dell'implementazione delle transazioni pubbliche servono almeno:

1. Prova HTTP/PHP fresca che dimostri lock condiviso per tutta la richiesta,
   marker di manutenzione e rifiuto delle nuove richieste.
2. Prova che il lock esclusivo CLI dreni le richieste già iniziate, con timeout
   finito e recupero del marker dopo interruzione.
3. Evidenza su IONOS che OPcache non continui a servire codice differente tra
   worker dopo la sostituzione e il rilascio del lock.
4. Implementazione e test Linux del journal/state writer, della transazione
   pubblica, dell'health check e del rollback, senza usare le fixture come
   publisher.
5. Revisione indipendente della provenance e configurazione verificata dei
   revisori dell'Environment `ionos-private-staging`.
6. Writer transazionale per release successive, rollback e recovery coerenti con
   current-release/journal e backup freschi.
7. Prova reale su PHP web IONOS della barriera, del drain e del comportamento
   OPcache prima di qualsiasi scrittura pubblica.

Fino ad allora i push su `main` eseguono CI e build dell'artefatto. Il trasferimento
privato è manuale e richiede l'Environment protetto; non è configurato deploy
automatico e nessun job modifica WordPress pubblico.
