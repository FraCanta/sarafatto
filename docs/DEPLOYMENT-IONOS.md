# Anteprima rilascio IONOS

Questa fase prepara e confronta una release, ma non pubblica file. Il workflow ha esclusivamente il trigger `workflow_dispatch`; non contiene una modalità di deploy reale.

## Percorsi e protezioni

Il pacchetto comprende `themes/sarafatto/`, `plugins/sarafatto-core/` e il solo `mu-plugins/sarafatto-polylang-front-page-url.php`. Viene creato da `git archive` sul commit autorizzato, quindi non include modifiche locali non committate, `uploads`, plugin o temi non allowlisted, configurazioni o file `.env`. La build Vite sostituisce soltanto `themes/sarafatto/assets/dist` nell'artefatto temporaneo.

Sul server vengono letti esclusivamente `/home/www/public/wp-content/themes/sarafatto`, `plugins/sarafatto-core` e il singolo MU plugin elencato. Lo script acquisisce hash e inventario; tre invocazioni `rsync` usano sempre `--dry-run`, senza `--delete`. Non viene eseguito `git pull`, né alcuna scrittura in `/home/www/public`.

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

Da Actions avviare **IONOS deployment preview** sul branch `main` e inserire lo SHA completo del commit selezionato. Il workflow si arresta se branch, SHA o build non coincidono, se il manifest o un asset manca, se l'artefatto esce dall'allowlist, se vi sono symlink nelle directory remote autorizzate o se SSH/rsync fallisce.

Il riepilogo del job riporta file nuovi, modificati, invariati, presenti soltanto in produzione (mai eliminati), drift dalla baseline e righe `rsync --dry-run`. In assenza di `/home/www/sarafatto-deploy/state/production-inventory.tsv` non è possibile distinguere modifiche manuali da divergenze di release. Questa fase non crea tale baseline.

## Seguito del progetto

Prima di abilitare qualsiasi pubblicazione servono una baseline approvata, backup con verifica e retention, protezione GitHub Environment con approvazione, pubblicazione atomica/ordinata di tema e plugin, controlli HTTP, verifica hash post-pubblicazione e una procedura di rollback provata. Queste capacità non fanno parte di questa anteprima.
