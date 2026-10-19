<?php
/** Shared filters form for desktop sidebar and mobile disclosure. */
$args = wp_parse_args(
	$args,
	array(
		'archive_url'       => get_post_type_archive_link( 'sarafatto_prodotto' ),
		'categories'        => array(),
		'gift_ideas'        => array(),
		'selected_cat'      => null,
		'selected_gift'     => null,
		'personalizable'    => false,
		'all_filters_active' => false,
		'sort'              => 'recenti',
		'category_context'  => false,
		'all_products_url' => '',
		'occasions'         => array(),
		'selected_occasion' => null,
	)
);
?>
<form class="product-filters__form" method="get" action="<?php echo esc_url( $args['archive_url'] ); ?>">
	<?php if ( 'recenti' !== $args['sort'] ) : ?><input type="hidden" name="ordina" value="<?php echo esc_attr( $args['sort'] ); ?>"><?php endif; ?>
	<?php if ( ! $args['category_context'] ) : ?>
	<fieldset class="product-filters__group">
		<legend><?php echo esc_html( sarafatto_theme_label( 'Categorie', 'Categories' ) ); ?></legend>
		<ul class="product-filters__list">
			<li><a class="product-filters__all<?php echo ! $args['all_filters_active'] ? ' is-current' : ''; ?>" href="<?php echo esc_url( $args['all_products_url'] ? $args['all_products_url'] : $args['archive_url'] ); ?>"<?php echo ! $args['all_filters_active'] ? ' aria-current="page"' : ''; ?>><?php echo esc_html( sarafatto_theme_label( 'Tutti i prodotti', 'All products' ) ); ?></a></li>
			<?php foreach ( $args['categories'] as $term ) : ?>
				<li><label class="product-filters__option"><input type="radio" name="categoria" value="<?php echo esc_attr( $term->slug ); ?>" <?php checked( $args['selected_cat'] instanceof WP_Term && (int) $args['selected_cat']->term_id === (int) $term->term_id ); ?>><span><?php echo esc_html( $term->name ); ?></span></label></li>
			<?php endforeach; ?>
		</ul>
	</fieldset>
	<?php endif; ?>
	<?php if ( $args['gift_ideas'] ) : ?>
		<fieldset class="product-filters__group">
			<legend><?php echo esc_html( sarafatto_theme_label( 'Idee regalo', 'Gift ideas' ) ); ?></legend>
			<ul class="product-filters__list">
				<?php foreach ( $args['gift_ideas'] as $term ) : ?>
					<li><label class="product-filters__option"><input type="radio" name="idea" value="<?php echo esc_attr( $term->slug ); ?>" <?php checked( $args['selected_gift'] instanceof WP_Term && (int) $args['selected_gift']->term_id === (int) $term->term_id ); ?>><span><?php echo esc_html( $term->name ); ?></span></label></li>
				<?php endforeach; ?>
			</ul>
		</fieldset>
	<?php endif; ?>
	<?php if ( $args['occasions'] ) : ?>
		<fieldset class="product-filters__group">
			<legend><?php echo esc_html( sarafatto_theme_label( 'Occasioni', 'Occasions' ) ); ?></legend>
			<ul class="product-filters__list">
				<?php foreach ( $args['occasions'] as $term ) : ?>
					<li><label class="product-filters__option"><input type="radio" name="occasione" value="<?php echo esc_attr( $term->slug ); ?>" <?php checked( $args['selected_occasion'] instanceof WP_Term && (int) $args['selected_occasion']->term_id === (int) $term->term_id ); ?>><span><?php echo esc_html( $term->name ); ?></span></label></li>
				<?php endforeach; ?>
			</ul>
		</fieldset>
	<?php endif; ?>
	<fieldset class="product-filters__group">
		<legend><?php echo esc_html( sarafatto_theme_label( 'Personalizzabili', 'Customisable' ) ); ?></legend>
		<label class="product-filters__option"><input type="checkbox" name="personalizzabili" value="1" <?php checked( $args['personalizable'] ); ?>><span><?php echo esc_html( sarafatto_theme_label( 'Personalizzabili', 'Customisable' ) ); ?></span></label>
	</fieldset>
	<button class="button button--secondary button--sm product-filters__submit" type="submit"><?php echo esc_html( sarafatto_theme_label( 'Applica filtri', 'Apply filters' ) ); ?></button>
	<?php if ( $args['category_context'] && $args['all_products_url'] ) : ?>
		<a class="product-filters__reset" href="<?php echo esc_url( $args['archive_url'] ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Azzera filtri', 'Clear filters' ) ); ?></a>
	<?php endif; ?>
</form>
