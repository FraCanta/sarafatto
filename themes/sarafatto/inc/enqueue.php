<?php
/** Front-end assets and Vite development integration. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_enqueue_assets() {
	$hot_file = get_theme_file_path( '/hot' );
	if ( is_readable( $hot_file ) ) {
		$dev_server = trim( file_get_contents( $hot_file ) ); // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions
		if ( $dev_server ) {
			wp_enqueue_script_module( 'sarafatto-vite-client', esc_url( $dev_server . '/@vite/client' ) );
			wp_enqueue_script_module( 'sarafatto-app', esc_url( $dev_server . '/assets/src/js/app.js' ), array( 'sarafatto-vite-client' ) );
			return;
		}
	}

	$manifest = sarafatto_asset_manifest();
	$entry    = $manifest['assets/src/js/app.js'] ?? null;
	if ( ! is_array( $entry ) || empty( $entry['file'] ) ) {
		return;
	}

	$base_url = get_theme_file_uri( '/assets/dist/' );
	if ( ! empty( $entry['css'] ) ) {
		foreach ( $entry['css'] as $index => $css_file ) {
			wp_enqueue_style( 'sarafatto-app-' . $index, esc_url( $base_url . $css_file ), array(), null );
		}
	}
	wp_enqueue_script_module( 'sarafatto-app', esc_url( $base_url . $entry['file'] ) );
}
add_action( 'wp_enqueue_scripts', 'sarafatto_enqueue_assets' );
