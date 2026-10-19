<?php
/**
 * Plugin Name: Saràfatto Core
 * Description: Funzionalità e modello contenuti del progetto Saràfatto.
 * Version: 1.0.0
 * Requires at least: 6.5
 * Requires PHP: 8.0
 * Text Domain: sarafatto-core
 *
 * @package SarafattoCore
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'SARAFATTO_CORE_VERSION', '1.0.0' );
define( 'SARAFATTO_CORE_PATH', plugin_dir_path( __FILE__ ) );
define( 'SARAFATTO_CORE_URL', plugin_dir_url( __FILE__ ) );

/** Grant settings access once on existing installs, matching plugin activation. */
function sarafatto_core_migrate_settings_capability() {
	if ( SARAFATTO_CORE_VERSION === get_option( 'sarafatto_settings_capability_migrated' ) ) {
		return;
	}

	$administrator = get_role( 'administrator' );
	$editor        = get_role( 'editor' );
	if ( ! $administrator ) {
		return;
	}

	$administrator->add_cap( 'manage_sarafatto_settings' );
	if ( $editor ) {
		$editor->add_cap( 'manage_sarafatto_settings' );
	}
	update_option( 'sarafatto_settings_capability_migrated', SARAFATTO_CORE_VERSION, false );
}
add_action( 'plugins_loaded', 'sarafatto_core_migrate_settings_capability', 0 );

function sarafatto_core_activate() {
	$settings_capability = 'manage_sarafatto_settings';
	$administrator       = get_role( 'administrator' );
	$editor               = get_role( 'editor' );

	if ( $administrator ) {
		$administrator->add_cap( $settings_capability );
	}
	if ( $editor ) {
		$editor->add_cap( $settings_capability );
	}
	update_option( 'sarafatto_settings_capability_migrated', SARAFATTO_CORE_VERSION, false );
}
register_activation_hook( __FILE__, 'sarafatto_core_activate' );

require_once SARAFATTO_CORE_PATH . 'includes/helpers.php';
require_once SARAFATTO_CORE_PATH . 'includes/multilingual.php';
require_once SARAFATTO_CORE_PATH . 'includes/post-types.php';
require_once SARAFATTO_CORE_PATH . 'includes/taxonomies.php';
require_once SARAFATTO_CORE_PATH . 'includes/settings.php';
require_once SARAFATTO_CORE_PATH . 'includes/home-personalized.php';
require_once SARAFATTO_CORE_PATH . 'includes/meta.php';
require_once SARAFATTO_CORE_PATH . 'includes/dev-dummy-data.php';
require_once SARAFATTO_CORE_PATH . 'includes/term-meta.php';
require_once SARAFATTO_CORE_PATH . 'includes/category-image.php';
require_once SARAFATTO_CORE_PATH . 'includes/metaboxes.php';
require_once SARAFATTO_CORE_PATH . 'includes/products-archive.php';
require_once SARAFATTO_CORE_PATH . 'includes/home-hero.php';
