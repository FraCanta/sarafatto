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
