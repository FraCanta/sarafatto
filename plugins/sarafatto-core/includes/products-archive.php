<?php
/** Product archive filters and query behavior. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Return a valid current-language term selected from a public archive filter. */
function sarafatto_get_archive_filter_term( $key, $taxonomy ) {
	if ( ! isset( $_GET[ $key ] ) || ! is_scalar( $_GET[ $key ] ) ) { // phpcs:ignore WordPress.Security.NonceVerification.Recommended
		return null;
	}
	$slug = sanitize_title( wp_unslash( $_GET[ $key ] ) ); // phpcs:ignore WordPress.Security.NonceVerification.Recommended
	$term = '' !== $slug ? get_term_by( 'slug', $slug, $taxonomy ) : null;
	if ( ! $term instanceof WP_Term ) {
		return null;
	}
	if ( function_exists( 'pll_get_term_language' ) && sarafatto_get_current_language() !== pll_get_term_language( $term->term_id, 'slug' ) ) {
		return null;
	}
	return $term;
}

/** Apply the catalog filters to the native archive query. */
function sarafatto_filter_product_archive_query( $query ) {
	if ( is_admin() || ! $query instanceof WP_Query || ! $query->is_main_query() || ! $query->is_post_type_archive( 'sarafatto_prodotto' ) ) {
		return;
	}

	$query->set( 'posts_per_page', 12 );
	$tax_query = array();
	foreach ( array( 'categoria' => 'sarafatto_categoria', 'idea' => 'sarafatto_idea_regalo' ) as $key => $taxonomy ) {
		$term = sarafatto_get_archive_filter_term( $key, $taxonomy );
		if ( $term instanceof WP_Term ) {
			$tax_query[] = array(
				'taxonomy' => $taxonomy,
				'field'    => 'term_id',
				'terms'    => $term->term_id,
			);
		}
	}
	if ( $tax_query ) {
		$query->set( 'tax_query', $tax_query );
	}

	$meta_query = array();
	if ( isset( $_GET['personalizzabili'] ) && '1' === sanitize_text_field( wp_unslash( $_GET['personalizzabili'] ) ) ) { // phpcs:ignore WordPress.Security.NonceVerification.Recommended
		$meta_query[] = array( 'key' => 'sarafatto_personalizable', 'value' => '1' );
	}
	if ( $meta_query ) {
		$query->set( 'meta_query', $meta_query );
	}

	$sort = isset( $_GET['ordina'] ) && is_scalar( $_GET['ordina'] ) ? sanitize_key( wp_unslash( $_GET['ordina'] ) ) : 'recenti'; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
	$sort_options = array(
		'recenti'       => array( 'date', 'DESC' ),
		'meno-recenti'  => array( 'date', 'ASC' ),
		'prezzo-crescente'  => array( 'price', 'ASC' ),
		'prezzo-decrescente' => array( 'price', 'DESC' ),
	);
	if ( ! isset( $sort_options[ $sort ] ) ) {
		$sort = 'recenti';
	}
	list( $orderby, $order ) = $sort_options[ $sort ];
	$query->set( 'orderby', 'date' );
	$query->set( 'order', 'price' === $orderby ? 'DESC' : $order );
	$query->set( 'sarafatto_price_sort', 'price' === $orderby ? $order : '' );
}
add_action( 'pre_get_posts', 'sarafatto_filter_product_archive_query' );

/** Sort by the normalized optional price while keeping products with no price in the result. */
function sarafatto_order_product_archive_by_price( $clauses, $query ) {
	if ( is_admin() || ! $query instanceof WP_Query || ! $query->is_main_query() || ! $query->is_post_type_archive( 'sarafatto_prodotto' ) ) {
		return $clauses;
	}
	$order = $query->get( 'sarafatto_price_sort' );
	if ( ! in_array( $order, array( 'ASC', 'DESC' ), true ) ) {
		return $clauses;
	}
	global $wpdb;
	$price_sql = "(SELECT CAST(NULLIF(pm.meta_value, '') AS DECIMAL(12,2)) FROM {$wpdb->postmeta} pm WHERE pm.post_id = {$wpdb->posts}.ID AND pm.meta_key = 'sarafatto_price' LIMIT 1)";
	$clauses['orderby'] = $price_sql . ' ' . $order . ", {$wpdb->posts}.post_date DESC";
	return $clauses;
}
add_filter( 'posts_clauses', 'sarafatto_order_product_archive_by_price', 10, 2 );

/** Return visible, current-language terms for a catalog filter. */
function sarafatto_get_product_archive_terms( $taxonomy ) {
	$terms = get_terms(
		sarafatto_add_language_to_query_args(
			array(
				'taxonomy'   => $taxonomy,
				'hide_empty' => true,
				'orderby'    => 'name',
				'order'      => 'ASC',
			)
		)
	);
	return is_wp_error( $terms ) ? array() : $terms;
}

/** Find a shared attachment by its original uploaded filename. */
function sarafatto_get_product_archive_banner_id() {
	$ids = get_posts(
		array(
			'post_type'        => 'attachment',
			'post_status'      => 'inherit',
			'posts_per_page'   => 1,
			'fields'           => 'ids',
			'suppress_filters' => true,
			'meta_query'       => array(
				array(
					'key'     => '_wp_attached_file',
					'value'   => 'banner_prodotti.png',
				'compare' => 'LIKE',
			),
			),
		)
	);
	return $ids ? absint( $ids[0] ) : 0;
}
