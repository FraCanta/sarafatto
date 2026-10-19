<?php
/** Shared catalog pagination preserving active filters. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$args = wp_parse_args( $args, array( 'query' => $GLOBALS['wp_query'], 'selected_cat' => null, 'selected_gift' => null, 'selected_occasion' => null, 'personalizable' => false, 'sort' => 'recenti' ) );
$query = $args['query'] instanceof WP_Query ? $args['query'] : $GLOBALS['wp_query'];
$pagination = paginate_links(
	array(
		'total'     => (int) $query->max_num_pages,
		'current'   => max( 1, get_query_var( 'paged' ) ),
		'type'      => 'list',
		'prev_text' => sarafatto_theme_label( '← Precedente', '← Previous' ),
		'next_text' => sarafatto_theme_label( 'Successiva →', 'Next →' ),
		'add_args'  => array_filter(
			array(
				'categoria'         => $args['selected_cat'] instanceof WP_Term ? $args['selected_cat']->slug : '',
				'idea'              => $args['selected_gift'] instanceof WP_Term ? $args['selected_gift']->slug : '',
				'occasione'         => $args['selected_occasion'] instanceof WP_Term ? $args['selected_occasion']->slug : '',
				'personalizzabili'  => $args['personalizable'] ? '1' : '',
				'ordina'            => 'recenti' !== $args['sort'] ? $args['sort'] : '',
			)
		),
	)
);
if ( $pagination ) :
	?>
	<nav class="product-pagination" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Paginazione prodotti', 'Product pagination' ) ); ?>"><?php echo wp_kses_post( $pagination ); ?></nav>
<?php endif; ?>
