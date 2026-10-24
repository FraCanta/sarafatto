<?php
/** Front-end assets and Vite development integration. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Collect CSS files for an entry and its statically imported Vite chunks. */
function sarafatto_collect_vite_entry_css( $entry_key, $manifest, &$css_files, &$visited_entries ) {
	if (
		isset( $visited_entries[ $entry_key ] )
		|| ! isset( $manifest[ $entry_key ] )
		|| ! is_array( $manifest[ $entry_key ] )
	) {
		return;
	}
	$visited_entries[ $entry_key ] = true;
	$entry = $manifest[ $entry_key ];

	if ( ! empty( $entry['css'] ) && is_array( $entry['css'] ) ) {
		foreach ( $entry['css'] as $css_file ) {
			$css_files[ $css_file ] = true;
		}
	}

	if ( ! empty( $entry['imports'] ) && is_array( $entry['imports'] ) ) {
		foreach ( $entry['imports'] as $import_key ) {
			sarafatto_collect_vite_entry_css( $import_key, $manifest, $css_files, $visited_entries );
		}
	}
}

/** Enqueue one Vite entry and its transitive CSS without repeating styles. */
function sarafatto_enqueue_vite_entry( $handle, $entry_key, $manifest, $base_url ) {
	$entry = $manifest[ $entry_key ] ?? null;
	if ( ! is_array( $entry ) || empty( $entry['file'] ) ) {
		return false;
	}

	static $enqueued_css = array();
	$entry_css = array();
	$visited_entries = array();
	sarafatto_collect_vite_entry_css( $entry_key, $manifest, $entry_css, $visited_entries );
	foreach ( array_keys( $entry_css ) as $css_file ) {
		if ( isset( $enqueued_css[ $css_file ] ) ) {
			continue;
		}
		$enqueued_css[ $css_file ] = true;
		wp_enqueue_style(
			'sarafatto-app-' . count( $enqueued_css ),
			esc_url( $base_url . $css_file ),
			array(),
			null
		);
	}

	wp_enqueue_script_module(
		$handle,
		esc_url( $base_url . $entry['file'] ),
		array(),
		null
	);
	return true;
}

/** Select the page entrypoint from WordPress's resolved query condition. */
function sarafatto_page_script_entry() {
	if ( function_exists( 'is_front_page' ) && is_front_page() ) {
		return 'home';
	}
	if ( function_exists( 'is_singular' ) && is_singular( 'sarafatto_prodotto' ) ) {
		return 'product';
	}
	if ( function_exists( 'is_post_type_archive' ) && is_post_type_archive( 'sarafatto_prodotto' ) ) {
		return 'productArchive';
	}
	return '';
}

function sarafatto_enqueue_assets() {
	$page_entry = sarafatto_page_script_entry();
	$hot_file = get_theme_file_path( '/hot' );
	if ( is_readable( $hot_file ) ) {
		$dev_server = trim( file_get_contents( $hot_file ) ); // phpcs:ignore WordPress.PHP.DiscouragedPHPFunctions
		if ( $dev_server ) {
			wp_enqueue_script_module( 'sarafatto-vite-client', esc_url( $dev_server . '/@vite/client' ) );
			wp_enqueue_script_module( 'sarafatto-app', esc_url( $dev_server . '/assets/src/js/app.js' ), array( 'sarafatto-vite-client' ) );
			if ( $page_entry ) {
				$page_file = 'productArchive' === $page_entry ? 'product-archive' : $page_entry;
				wp_enqueue_script_module(
					'sarafatto-' . $page_entry,
					esc_url( $dev_server . '/assets/src/js/' . $page_file . '.js' )
				);
			}
			return;
		}
	}

	$manifest = sarafatto_asset_manifest();
	$base_url = get_theme_file_uri( '/assets/dist/' );
	sarafatto_enqueue_vite_entry( 'sarafatto-app', 'assets/src/js/app.js', $manifest, $base_url );
	if ( $page_entry ) {
		$page_keys = array(
			'home'          => 'assets/src/js/home.js',
			'product'       => 'assets/src/js/product.js',
			'productArchive' => 'assets/src/js/product-archive.js',
		);
		$page_key = $page_keys[ $page_entry ] ?? '';
		if ( $page_key ) {
			sarafatto_enqueue_vite_entry( 'sarafatto-' . $page_entry, $page_key, $manifest, $base_url );
		}
	}
}
add_action( 'wp_enqueue_scripts', 'sarafatto_enqueue_assets' );
