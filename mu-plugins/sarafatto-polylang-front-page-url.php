<?php
/** Keep Polylang's static front page at each language root URL. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Return a bounded, no-follow JSON document from the private deploy area. */
function sarafatto_deploy_barrier_read_private_json( $path, $expected_directory ) {
	$directory = rtrim( $expected_directory, '/' );
	if ( dirname( $path ) !== $directory || realpath( $directory ) !== $directory || is_link( $directory ) ) {
		return null;
	}

	$before = @lstat( $path ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged -- Missing configuration disables the barrier.
	if ( ! is_array( $before ) || 0100000 !== ( $before['mode'] & 0170000 ) || 1 !== $before['nlink'] || 0600 !== ( $before['mode'] & 0777 ) || $before['size'] > 4096 ) {
		return null;
	}

	$handle = @fopen( $path, 'rb' ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged -- Missing configuration disables the barrier.
	if ( ! is_resource( $handle ) ) {
		return null;
	}
	$opened = @fstat( $handle ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged -- A replaced file disables the barrier.
	if ( ! is_array( $opened ) || $opened['dev'] !== $before['dev'] || $opened['ino'] !== $before['ino'] || $opened['nlink'] !== 1 || ( $opened['mode'] & 0170000 ) !== 0100000 || ( $opened['mode'] & 0777 ) !== 0600 || $opened['size'] > 4096 ) {
		fclose( $handle );
		return null;
	}
	$raw = stream_get_contents( $handle, 4097 );
	fclose( $handle );
	if ( ! is_string( $raw ) || strlen( $raw ) > 4096 ) {
		return null;
	}
	$document = json_decode( $raw, true );
	return is_array( $document ) ? $document : null;
}

/** Validate the fixed opt-in configuration; absence or error leaves WordPress unchanged. */
function sarafatto_deploy_barrier_configuration() {
	$state_dir = '/home/www/sarafatto-deploy/state';
	$config    = sarafatto_deploy_barrier_read_private_json( $state_dir . '/request-barrier.json', $state_dir );
	$required  = array( 'schema_version', 'enabled', 'lock_path', 'window_path', 'status_token_sha256' );
	$keys      = is_array( $config ) ? array_keys( $config ) : array();
	sort( $keys );
	$expected  = $required;
	sort( $expected );
	if ( ! is_array( $config ) || $keys !== $expected || 1 !== ( $config['schema_version'] ?? null ) || ! is_bool( $config['enabled'] ?? null ) || '/home/www/sarafatto-deploy/locks/web-request.lock' !== ( $config['lock_path'] ?? '' ) || '/home/www/sarafatto-deploy/state/request-deploy-window.json' !== ( $config['window_path'] ?? '' ) || ! preg_match( '/\A[a-f0-9]{64}\z/', (string) ( $config['status_token_sha256'] ?? '' ) ) ) {
		return null;
	}
	return $config;
}

/** Read whether an explicitly armed private operation window exists. */
function sarafatto_deploy_barrier_window_is_armed() {
	$state_dir = '/home/www/sarafatto-deploy/state';
	$path      = $state_dir . '/request-deploy-window.json';
	if ( ! file_exists( $path ) && ! is_link( $path ) ) {
		return false;
	}
	// An existing marker, even an unreadable one, means an operation was armed.
	// Keep the fail-closed web response until an operator verifies recovery.
	return true;
}

/** Deny a WordPress request only inside an explicitly armed operation window. */
function sarafatto_deploy_barrier_maintenance_response() {
	http_response_code( 503 );
	header( 'Retry-After: 2' );
	header( 'Cache-Control: no-store, max-age=0' );
	header( 'X-Sarafatto-Deploy-Barrier: active' );
	exit( 'Servizio temporaneamente in manutenzione.' );
}

/** Acquire the request's shared lock when explicitly enabled. */
function sarafatto_deploy_barrier_bootstrap() {
	global $sarafatto_deploy_barrier_status;
	$sarafatto_deploy_barrier_status = array(
		'enabled'       => false,
		'lock_acquired' => false,
		'window_armed'  => sarafatto_deploy_barrier_window_is_armed(),
		'config_sha256' => '',
	);

	$environment = function_exists( 'wp_get_environment_type' ) ? wp_get_environment_type() : 'unknown';
	if ( 'cli' === PHP_SAPI ) {
		return;
	}
	if ( $sarafatto_deploy_barrier_status['window_armed'] ) {
		sarafatto_deploy_barrier_maintenance_response();
	}
	if ( 'production' !== $environment ) {
		// Recheck before leaving the opt-in path in case a window was just armed.
		if ( sarafatto_deploy_barrier_window_is_armed() ) {
			sarafatto_deploy_barrier_maintenance_response();
		}
		return;
	}

	$config = sarafatto_deploy_barrier_configuration();
	if ( ! is_array( $config ) ) {
		if ( sarafatto_deploy_barrier_window_is_armed() ) {
			sarafatto_deploy_barrier_maintenance_response();
		}
		return;
	}
	$sarafatto_deploy_barrier_status['config_sha256'] = hash_file( 'sha256', '/home/www/sarafatto-deploy/state/request-barrier.json' );
	$sarafatto_deploy_barrier_status['enabled'] = $config['enabled'];

	$lock_path = $config['lock_path'];
	$before    = @lstat( $lock_path ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged -- Failure must not affect the existing site outside an armed window.
	$handle    = @fopen( $lock_path, 'rb' ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged -- Failure must not affect the existing site outside an armed window.
	$opened    = is_resource( $handle ) ? @fstat( $handle ) : false; // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged -- Failure must not affect the existing site outside an armed window.
	$valid     = is_array( $before ) && is_array( $opened )
		&& 0100000 === ( $before['mode'] & 0170000 ) && 0100000 === ( $opened['mode'] & 0170000 )
		&& 1 === $before['nlink'] && 1 === $opened['nlink']
		&& 0600 === ( $before['mode'] & 0777 ) && 0600 === ( $opened['mode'] & 0777 )
		&& $before['dev'] === $opened['dev'] && $before['ino'] === $opened['ino'];

	if ( $valid && flock( $handle, LOCK_SH | LOCK_NB ) ) {
		// Pair the initial marker check with this post-lock check. If the marker
		// appeared meanwhile, release the reader before denying the request.
		$sarafatto_deploy_barrier_status['window_armed'] = sarafatto_deploy_barrier_window_is_armed();
		if ( $sarafatto_deploy_barrier_status['window_armed'] ) {
			flock( $handle, LOCK_UN );
			fclose( $handle );
			sarafatto_deploy_barrier_maintenance_response();
		}
		$sarafatto_deploy_barrier_status['lock_accessible'] = true;
		if ( $config['enabled'] ) {
			$sarafatto_deploy_barrier_status['lock_acquired'] = true;
			register_shutdown_function(
				static function () use ( $handle ) {
					flock( $handle, LOCK_UN );
					fclose( $handle );
				}
			);
		} else {
			flock( $handle, LOCK_UN );
			fclose( $handle );
		}
		return;
	}

	if ( is_resource( $handle ) ) {
		fclose( $handle );
	}
	$sarafatto_deploy_barrier_status['window_armed'] = sarafatto_deploy_barrier_window_is_armed();
	if ( $sarafatto_deploy_barrier_status['window_armed'] ) {
		sarafatto_deploy_barrier_maintenance_response();
	}
}
sarafatto_deploy_barrier_bootstrap();

/** Register an authenticated, read-only status endpoint for PHP web verification. */
function sarafatto_register_deploy_barrier_status_route() {
	register_rest_route(
		'sarafatto/v1',
		'/deploy-barrier',
		array(
			'methods'             => 'GET',
			'permission_callback' => 'sarafatto_authorize_deploy_barrier_status',
			'callback'            => 'sarafatto_get_deploy_barrier_status',
		)
	);
}
add_action( 'rest_api_init', 'sarafatto_register_deploy_barrier_status_route' );

function sarafatto_authorize_deploy_barrier_status( $request ) {
	$config = sarafatto_deploy_barrier_configuration();
	$token  = $request->get_header( 'x-sarafatto-barrier-token' );
	return is_array( $config ) && is_string( $token ) && hash_equals( $config['status_token_sha256'], hash( 'sha256', $token ) );
}

function sarafatto_get_deploy_barrier_status( $request ) {
	global $sarafatto_deploy_barrier_status;
	$hold_ms = filter_var( $request->get_param( 'hold_ms' ), FILTER_VALIDATE_INT );
	if ( false !== $hold_ms && $hold_ms > 0 && $hold_ms <= 2000 && ! empty( $sarafatto_deploy_barrier_status['lock_acquired'] ) ) {
		usleep( $hold_ms * 1000 );
	}
	$opcache_status = function_exists( 'opcache_get_status' ) ? @opcache_get_status( false ) : false; // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged -- Status-only probe.
	$response = rest_ensure_response(
		array(
			'schema_version' => 1,
			'enabled'        => ! empty( $sarafatto_deploy_barrier_status['enabled'] ),
			'lock_accessible' => ! empty( $sarafatto_deploy_barrier_status['lock_accessible'] ),
			'lock_acquired'  => ! empty( $sarafatto_deploy_barrier_status['lock_acquired'] ),
			'window_armed'   => ! empty( $sarafatto_deploy_barrier_status['window_armed'] ),
			'php_sapi'       => PHP_SAPI,
			'php_version'    => PHP_VERSION,
			'source_sha256'  => hash_file( 'sha256', __FILE__ ),
			'config_sha256'  => (string) ( $sarafatto_deploy_barrier_status['config_sha256'] ?? '' ),
			'opcache'        => array(
				'enabled'             => is_array( $opcache_status ) && ! empty( $opcache_status['opcache_enabled'] ),
				'validate_timestamps' => ini_get( 'opcache.validate_timestamps' ),
				'revalidate_freq'     => ini_get( 'opcache.revalidate_freq' ),
				'realpath_cache_ttl'  => ini_get( 'realpath_cache_ttl' ),
			),
		)
	);
	$response->header( 'Cache-Control', 'no-store, max-age=0' );
	return $response;
}

/** Apply Polylang's built-in language-root front page behavior without saving its option. */
function sarafatto_polylang_language_root_front_page_option( $options ) {
	if ( ! is_array( $options ) || 'page' !== get_option( 'show_on_front' ) ) {
		return $options;
	}

	$options['redirect_lang'] = 1;
	return $options;
}
add_filter( 'option_polylang', 'sarafatto_polylang_language_root_front_page_option' );
