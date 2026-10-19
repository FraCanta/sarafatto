<?php
/** Shared catalog count and ordering controls. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$args = wp_parse_args( $args, array( 'action_url' => get_post_type_archive_link( 'sarafatto_prodotto' ), 'selected_cat' => null, 'selected_gift' => null, 'selected_occasion' => null, 'personalizable' => false, 'category_context' => false, 'filters' => array() ) );
$query = isset( $args['query'] ) && $args['query'] instanceof WP_Query ? $args['query'] : $GLOBALS['wp_query'];
$sort  = function_exists( 'sarafatto_get_product_archive_sort' ) ? sarafatto_get_product_archive_sort() : 'recenti';
$sort_labels = array(
	'recenti'             => sarafatto_theme_label( 'Più recenti', 'Newest' ),
	'meno-recenti'        => sarafatto_theme_label( 'Meno recenti', 'Oldest' ),
	'prezzo-crescente'    => sarafatto_theme_label( 'Prezzo crescente', 'Price: low to high' ),
	'prezzo-decrescente'  => sarafatto_theme_label( 'Prezzo decrescente', 'Price: high to low' ),
);
?>
<div class="product-archive__toolbar">
	<?php get_template_part( 'template-parts/products/archive-count', null, array( 'query' => $query ) ); ?>
	<?php if ( $args['category_context'] ) : ?><div class="product-category-archive__toolbar-actions"><?php endif; ?>
	<?php if ( $args['category_context'] && $args['filters'] ) : ?>
			<details class="product-category-filters">
				<summary class="product-category-filters__toggle"><span><?php echo esc_html( sarafatto_theme_label( 'Filtra', 'Filter' ) ); ?></span><span aria-hidden="true">+</span></summary>
				<?php get_template_part( 'template-parts/products/archive-filters', null, $args['filters'] ); ?>
			</details>
	<?php endif; ?>
	<form class="product-sort" method="get" action="<?php echo esc_url( $args['action_url'] ); ?>">
		<?php if ( ! $args['category_context'] && $args['selected_cat'] instanceof WP_Term ) : ?><input type="hidden" name="categoria" value="<?php echo esc_attr( $args['selected_cat']->slug ); ?>"><?php endif; ?>
		<?php if ( $args['selected_gift'] instanceof WP_Term ) : ?><input type="hidden" name="idea" value="<?php echo esc_attr( $args['selected_gift']->slug ); ?>"><?php endif; ?>
		<?php if ( $args['selected_occasion'] instanceof WP_Term ) : ?><input type="hidden" name="occasione" value="<?php echo esc_attr( $args['selected_occasion']->slug ); ?>"><?php endif; ?>
		<?php if ( $args['personalizable'] ) : ?><input type="hidden" name="personalizzabili" value="1"><?php endif; ?>
		<label for="product-sort-select"><?php echo esc_html( sarafatto_theme_label( 'Ordina per', 'Sort by' ) ); ?></label>
		<select id="product-sort-select" name="ordina">
			<?php foreach ( $sort_labels as $value => $label ) : ?><option value="<?php echo esc_attr( $value ); ?>" <?php selected( $sort, $value ); ?>><?php echo esc_html( $label ); ?></option><?php endforeach; ?>
		</select>
		<button class="product-sort__submit" type="submit"><?php echo esc_html( sarafatto_theme_label( 'Ordina', 'Sort' ) ); ?></button>
	</form>
	<?php if ( $args['category_context'] ) : ?></div><?php endif; ?>
</div>
