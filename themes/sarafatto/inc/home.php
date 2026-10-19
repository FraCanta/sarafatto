<?php
/** Current-language data accessors for the Home page. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Return current-language product categories and their archive links. */
function sarafatto_get_home_categories( $limit = 0 ) {
	$args = array(
		'taxonomy'   => 'sarafatto_categoria',
		'hide_empty' => false,
		'orderby'    => 'term_order',
		'order'      => 'ASC',
		'number'     => absint( $limit ),
	);
	$args = function_exists( 'sarafatto_add_language_to_query_args' ) ? sarafatto_add_language_to_query_args( $args ) : $args;
	$terms = get_terms( $args );
	if ( is_wp_error( $terms ) || ! is_array( $terms ) ) {
		return array();
	}

	$categories = array();
	foreach ( $terms as $term ) {
		if ( ! $term instanceof WP_Term ) {
			continue;
		}
		$url = get_term_link( $term );
		if ( is_wp_error( $url ) ) {
			continue;
		}
		$categories[] = array(
			'term'     => $term,
			'image_id' => function_exists( 'sarafatto_get_category_image_id' ) ? sarafatto_get_category_image_id( $term->term_id ) : 0,
			'url'      => $url,
		);
	}

	return $categories;
}

/** Return a short current-language product selection based on an existing editorial flag. */
function sarafatto_get_home_product_selection( $meta_key, $limit = 4 ) {
	if ( ! in_array( $meta_key, array( 'sarafatto_is_featured', 'sarafatto_is_new' ), true ) ) {
		return array();
	}

	$args = array(
		'post_type'              => 'sarafatto_prodotto',
		'post_status'            => 'publish',
		'posts_per_page'         => max( 1, absint( $limit ) ),
		'no_found_rows'          => true,
		'ignore_sticky_posts'    => true,
		'update_post_meta_cache' => true,
		'update_post_term_cache' => false,
		'orderby'                => array( 'menu_order' => 'ASC', 'date' => 'DESC' ),
		'meta_query'             => array(
			array(
				'key'     => $meta_key,
				'value'   => '1',
				'compare' => '=',
			),
		),
	);
	$args = function_exists( 'sarafatto_add_language_to_query_args' ) ? sarafatto_add_language_to_query_args( $args ) : $args;
	$query = new WP_Query( $args );
	return $query->posts;
}

/** Return current-language gift-idea terms that have published products assigned. */
function sarafatto_get_home_gift_ideas( $limit = 2 ) {
	$args = array(
		'taxonomy'   => 'sarafatto_idea_regalo',
		'hide_empty' => true,
		'orderby'    => 'term_order',
		'order'      => 'ASC',
		'number'     => max( 1, absint( $limit ) ),
	);
	$args = function_exists( 'sarafatto_add_language_to_query_args' ) ? sarafatto_add_language_to_query_args( $args ) : $args;
	$terms = get_terms( $args );
	if ( is_wp_error( $terms ) || ! is_array( $terms ) ) {
		return array();
	}

	$ideas = array();
	foreach ( $terms as $term ) {
		if ( ! $term instanceof WP_Term ) {
			continue;
		}
		$url = get_term_link( $term );
		if ( is_wp_error( $url ) ) {
			continue;
		}
		$ideas[] = array(
			'term'  => $term,
			'url'   => $url,
			'title' => function_exists( 'sarafatto_get_gift_idea_display_title' ) ? sarafatto_get_gift_idea_display_title( $term->term_id ) : $term->name,
			'image' => function_exists( 'sarafatto_get_gift_idea_image_id' ) ? sarafatto_get_gift_idea_image_id( $term->term_id ) : 0,
			'icon'  => function_exists( 'sarafatto_get_gift_idea_icon' ) ? sarafatto_get_gift_idea_icon( $term->term_id ) : '',
		);
	}

	return $ideas;
}
