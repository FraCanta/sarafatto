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
	if ( is_admin() || ! $query instanceof WP_Query || ! $query->is_main_query() ) {
		return;
	}
	$is_product_archive = $query->is_post_type_archive( 'sarafatto_prodotto' );
	$is_category_archive = $query->is_tax( 'sarafatto_categoria' );
	if ( ! $is_product_archive && ! $is_category_archive ) {
		return;
	}

	$query->set( 'posts_per_page', 12 );
	$tax_query = array( 'relation' => 'AND' );
	if ( $is_category_archive ) {
		$current_term = get_queried_object();
		if ( ! $current_term instanceof WP_Term && 'sarafatto_categoria' === $query->get( 'taxonomy' ) ) {
			$current_term = get_term_by( 'slug', sanitize_title( $query->get( 'term' ) ), 'sarafatto_categoria' );
		}
		if ( $current_term instanceof WP_Term && 'sarafatto_categoria' === $current_term->taxonomy ) {
			$tax_query[] = array(
				'taxonomy'         => 'sarafatto_categoria',
				'field'            => 'term_id',
				'terms'            => $current_term->term_id,
				'include_children' => true,
			);
		}
	} else {
		$category = sarafatto_get_archive_filter_term( 'categoria', 'sarafatto_categoria' );
		if ( $category instanceof WP_Term ) {
			$tax_query[] = array(
				'taxonomy' => 'sarafatto_categoria',
				'field'    => 'term_id',
				'terms'    => $category->term_id,
			);
		}
	}
	$gift_idea = sarafatto_get_archive_filter_term( 'idea', 'sarafatto_idea_regalo' );
	if ( $gift_idea instanceof WP_Term ) {
		$tax_query[] = array(
			'taxonomy' => 'sarafatto_idea_regalo',
			'field'    => 'term_id',
			'terms'    => $gift_idea->term_id,
		);
	}
	$occasion = sarafatto_get_archive_filter_term( 'occasione', 'sarafatto_occasione' );
	if ( $occasion instanceof WP_Term ) {
		$tax_query[] = array(
			'taxonomy' => 'sarafatto_occasione',
			'field'    => 'term_id',
			'terms'    => $occasion->term_id,
		);
	}
	if ( count( $tax_query ) > 1 ) {
		$query->set( 'tax_query', $tax_query );
	}

	$meta_query = array();
	if ( isset( $_GET['personalizzabili'] ) && is_scalar( $_GET['personalizzabili'] ) && '1' === sanitize_text_field( wp_unslash( $_GET['personalizzabili'] ) ) ) { // phpcs:ignore WordPress.Security.NonceVerification.Recommended
		$meta_query[] = array( 'key' => 'sarafatto_personalizable', 'value' => '1' );
	}
	if ( $meta_query ) {
		$query->set( 'meta_query', $meta_query );
	}

	$sort_options = array(
		'recenti'       => array( 'date', 'DESC' ),
		'meno-recenti'  => array( 'date', 'ASC' ),
		'prezzo-crescente'  => array( 'price', 'ASC' ),
		'prezzo-decrescente' => array( 'price', 'DESC' ),
	);
	$sort = sarafatto_get_product_archive_sort( array_keys( $sort_options ) );
	list( $orderby, $order ) = $sort_options[ $sort ];
	$query->set( 'orderby', 'date' );
	$query->set( 'order', 'price' === $orderby ? 'DESC' : $order );
	$query->set( 'sarafatto_price_sort', 'price' === $orderby ? $order : '' );
}
add_action( 'pre_get_posts', 'sarafatto_filter_product_archive_query' );

/** Sort by the normalized optional price while keeping products with no price in the result. */
function sarafatto_order_product_archive_by_price( $clauses, $query ) {
	if ( is_admin() || ! $query instanceof WP_Query || ! $query->is_main_query() || ( ! $query->is_post_type_archive( 'sarafatto_prodotto' ) && ! $query->is_tax( 'sarafatto_categoria' ) ) ) {
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
function sarafatto_get_product_archive_terms( $taxonomy, $hide_empty = true ) {
	$terms = get_terms(
		sarafatto_add_language_to_query_args(
			array(
				'taxonomy'   => $taxonomy,
				'hide_empty' => (bool) $hide_empty,
				'orderby'    => 'name',
				'order'      => 'ASC',
			)
		)
	);
	return is_wp_error( $terms ) ? array() : $terms;
}

/** Return the current archive sort key after validating it against supported options. */
function sarafatto_get_product_archive_sort( $allowed = array( 'recenti', 'meno-recenti', 'prezzo-crescente', 'prezzo-decrescente' ) ) {
	$sort = isset( $_GET['ordina'] ) && is_scalar( $_GET['ordina'] ) ? sanitize_key( wp_unslash( $_GET['ordina'] ) ) : 'recenti'; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
	return in_array( $sort, $allowed, true ) ? $sort : 'recenti';
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
