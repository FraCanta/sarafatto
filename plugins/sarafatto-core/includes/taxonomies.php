<?php
/** Register product classifications and editorial taxonomies. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_register_product_taxonomies() {
	$categories = array(
		'name'              => __( 'Categorie', 'sarafatto-core' ),
		'singular_name'     => __( 'Categoria', 'sarafatto-core' ),
		'menu_name'         => __( 'Categorie', 'sarafatto-core' ),
		'all_items'         => __( 'Tutte le categorie', 'sarafatto-core' ),
		'edit_item'         => __( 'Modifica categoria', 'sarafatto-core' ),
		'view_item'         => __( 'Visualizza categoria', 'sarafatto-core' ),
		'update_item'       => __( 'Aggiorna categoria', 'sarafatto-core' ),
		'add_new_item'      => __( 'Aggiungi categoria', 'sarafatto-core' ),
		'new_item_name'     => __( 'Nome nuova categoria', 'sarafatto-core' ),
		'parent_item'       => __( 'Categoria genitore', 'sarafatto-core' ),
		'parent_item_colon' => __( 'Categoria genitore:', 'sarafatto-core' ),
		'search_items'      => __( 'Cerca categorie', 'sarafatto-core' ),
		'not_found'         => __( 'Nessuna categoria trovata.', 'sarafatto-core' ),
	);
	register_taxonomy(
		'sarafatto_categoria',
		array( 'sarafatto_prodotto' ),
		array(
			'labels'            => $categories,
			'public'            => true,
			'hierarchical'      => true,
			'show_in_rest'      => false,
			'show_admin_column' => true,
			'rewrite'           => array( 'slug' => 'categoria', 'with_front' => false ),
		)
	);

	$occasions = array(
		'name'              => __( 'Occasioni', 'sarafatto-core' ),
		'singular_name'     => __( 'Occasione', 'sarafatto-core' ),
		'menu_name'         => __( 'Occasioni', 'sarafatto-core' ),
		'all_items'         => __( 'Tutte le occasioni', 'sarafatto-core' ),
		'edit_item'         => __( 'Modifica occasione', 'sarafatto-core' ),
		'view_item'         => __( 'Visualizza occasione', 'sarafatto-core' ),
		'update_item'       => __( 'Aggiorna occasione', 'sarafatto-core' ),
		'add_new_item'      => __( 'Aggiungi occasione', 'sarafatto-core' ),
		'new_item_name'     => __( 'Nome nuova occasione', 'sarafatto-core' ),
		'parent_item'       => __( 'Occasione genitore', 'sarafatto-core' ),
		'parent_item_colon' => __( 'Occasione genitore:', 'sarafatto-core' ),
		'search_items'      => __( 'Cerca occasioni', 'sarafatto-core' ),
		'not_found'         => __( 'Nessuna occasione trovata.', 'sarafatto-core' ),
	);
	register_taxonomy(
		'sarafatto_occasione',
		array( 'sarafatto_prodotto' ),
		array(
			'labels'            => $occasions,
			'public'            => true,
			'hierarchical'      => true,
			'show_in_rest'      => false,
			'show_admin_column' => true,
			'rewrite'           => array( 'slug' => 'occasioni', 'with_front' => false ),
		)
	);

	$gift_ideas = array(
		'name'              => __( 'Idee regalo', 'sarafatto-core' ),
		'singular_name'     => __( 'Idea regalo', 'sarafatto-core' ),
		'menu_name'         => __( 'Idee regalo', 'sarafatto-core' ),
		'all_items'         => __( 'Tutte le idee regalo', 'sarafatto-core' ),
		'edit_item'         => __( 'Modifica idea regalo', 'sarafatto-core' ),
		'view_item'         => __( 'Visualizza idea regalo', 'sarafatto-core' ),
		'update_item'       => __( 'Aggiorna idea regalo', 'sarafatto-core' ),
		'add_new_item'      => __( 'Aggiungi idea regalo', 'sarafatto-core' ),
		'new_item_name'     => __( 'Nome nuova idea regalo', 'sarafatto-core' ),
		'parent_item'       => __( 'Idea regalo genitore', 'sarafatto-core' ),
		'parent_item_colon' => __( 'Idea regalo genitore:', 'sarafatto-core' ),
		'search_items'      => __( 'Cerca idee regalo', 'sarafatto-core' ),
		'not_found'         => __( 'Nessuna idea regalo trovata.', 'sarafatto-core' ),
	);
	register_taxonomy(
		'sarafatto_idea_regalo',
		array( 'sarafatto_prodotto' ),
		array(
			'labels'            => $gift_ideas,
			'public'            => true,
			'hierarchical'      => true,
			'show_in_rest'      => false,
			'show_admin_column' => true,
			'rewrite'           => array( 'slug' => 'idee-regalo', 'with_front' => false ),
		)
	);
}
add_action( 'init', 'sarafatto_register_product_taxonomies', 6 );
