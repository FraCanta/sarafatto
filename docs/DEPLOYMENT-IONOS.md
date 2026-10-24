# Anteprima rilascio IONOS

Questa fase prepara e confronta una release, ma non pubblica file. Il workflow ha esclusivamente il trigger `workflow_dispatch`; non contiene una modalità di deploy reale.

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
