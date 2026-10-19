<?php
/** Shared catalog result count. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$args = wp_parse_args( $args, array( 'query' => $GLOBALS['wp_query'] ) );
$query = $args['query'] instanceof WP_Query ? $args['query'] : $GLOBALS['wp_query'];
?>
<p class="product-archive__count"><?php printf( esc_html( 1 === (int) $query->found_posts ? sarafatto_theme_label( '%s prodotto', '%s product' ) : sarafatto_theme_label( '%s prodotti', '%s products' ) ), esc_html( number_format_i18n( (int) $query->found_posts ) ) ); ?></p>
