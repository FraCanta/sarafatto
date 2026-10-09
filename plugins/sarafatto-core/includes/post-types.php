<?php
/** Register the primary product content type. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_register_product_post_type() {
	$labels = array(
		'name'                  => __( 'Prodotti', 'sarafatto-core' ),
		'singular_name'         => __( 'Prodotto', 'sarafatto-core' ),
		'menu_name'             => __( 'Prodotti', 'sarafatto-core' ),
		'name_admin_bar'        => __( 'Prodotto', 'sarafatto-core' ),
		'add_new'               => __( 'Aggiungi prodotto', 'sarafatto-core' ),
		'add_new_item'          => __( 'Aggiungi prodotto', 'sarafatto-core' ),
		'edit_item'             => __( 'Modifica prodotto', 'sarafatto-core' ),
		'new_item'              => __( 'Nuovo prodotto', 'sarafatto-core' ),
		'view_item'             => __( 'Visualizza prodotto', 'sarafatto-core' ),
		'view_items'            => __( 'Visualizza prodotti', 'sarafatto-core' ),
		'all_items'             => __( 'Tutti i prodotti', 'sarafatto-core' ),
		'search_items'          => __( 'Cerca prodotti', 'sarafatto-core' ),
		'not_found'             => __( 'Nessun prodotto trovato.', 'sarafatto-core' ),
		'not_found_in_trash'    => __( 'Nessun prodotto nel cestino.', 'sarafatto-core' ),
		'featured_image'        => __( 'Immagine principale', 'sarafatto-core' ),
		'set_featured_image'    => __( 'Imposta immagine principale', 'sarafatto-core' ),
		'remove_featured_image' => __( 'Rimuovi immagine principale', 'sarafatto-core' ),
		'use_featured_image'    => __( 'Usa come immagine principale', 'sarafatto-core' ),
		'archives'              => __( 'Archivio prodotti', 'sarafatto-core' ),
	);

	register_post_type(
		'sarafatto_prodotto',
		array(
			'labels'          => $labels,
			'public'          => true,
			'has_archive'     => true,
			'rewrite'         => array( 'slug' => 'prodotti', 'with_front' => false ),
			'show_in_rest'    => false,
			'menu_position'   => 20,
			'menu_icon'       => 'dashicons-products',
			'capability_type' => 'post',
			'map_meta_cap'    => true,
			'supports'        => array( 'title', 'excerpt', 'thumbnail', 'revisions' ),
		)
	);
}
add_action( 'init', 'sarafatto_register_product_post_type', 5 );

/** Keep the structured classic editor on Products. */
function sarafatto_disable_product_block_editor( $use_block_editor, $post_type ) {
	return 'sarafatto_prodotto' === $post_type ? false : $use_block_editor;
}
add_filter( 'use_block_editor_for_post_type', 'sarafatto_disable_product_block_editor', 10, 2 );

/** Sanitize the native product excerpt used by the structured form. */
function sarafatto_sanitize_product_excerpt( $data ) {
	if ( isset( $data['post_type'], $data['post_excerpt'] ) && 'sarafatto_prodotto' === $data['post_type'] ) {
		$data['post_excerpt'] = sanitize_textarea_field( $data['post_excerpt'] );
	}

	return $data;
}
add_filter( 'wp_insert_post_data', 'sarafatto_sanitize_product_excerpt' );

/** Pages use excerpts as editorial summaries in linked-page blocks and the Home hero. */
function sarafatto_add_page_excerpt_support() {
	add_post_type_support( 'page', 'excerpt' );
}
add_action( 'init', 'sarafatto_add_page_excerpt_support', 7 );
