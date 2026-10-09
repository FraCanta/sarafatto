<?php
/** Asset manifest helpers. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_asset_manifest() {
	$manifest_path = get_theme_file_path( '/assets/dist/.vite/manifest.json' );
	if ( ! is_readable( $manifest_path ) ) {
		return array();
	}
	$manifest = json_decode( file_get_contents( $manifest_path ), true ); // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions
	return is_array( $manifest ) ? $manifest : array();
}

/** Output the theme's static favicon set when WordPress has no Site Icon. */
function sarafatto_theme_site_icons() {
	$icon_base = trailingslashit( get_theme_file_uri( '/assets/icons' ) );

	echo '<meta name="apple-mobile-web-app-title" content="SaràFatto">' . "\n";

	// WordPress prints its own icon tags when a Site Icon is configured.
	if ( function_exists( 'has_site_icon' ) && has_site_icon() ) {
		return;
	}

	$icons = array(
		'<link rel="icon" type="image/png" href="' . esc_url( $icon_base . 'favicon-96x96.png' ) . '" sizes="96x96">',
		'<link rel="icon" type="image/svg+xml" href="' . esc_url( $icon_base . 'favicon.svg' ) . '">',
		'<link rel="shortcut icon" href="' . esc_url( $icon_base . 'favicon.ico' ) . '">',
		'<link rel="apple-touch-icon" sizes="180x180" href="' . esc_url( $icon_base . 'apple-touch-icon.png' ) . '">',
		'<link rel="manifest" href="' . esc_url( $icon_base . 'site.webmanifest' ) . '">',
	);

	echo implode( "\n", $icons ) . "\n"; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
}
add_action( 'wp_head', 'sarafatto_theme_site_icons', 2 );
