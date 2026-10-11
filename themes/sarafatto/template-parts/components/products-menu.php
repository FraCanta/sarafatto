<?php
/** Responsive editorial Products navigation panel. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$panel_id = isset( $args['panel_id'] ) ? sanitize_html_class( $args['panel_id'] ) : 'site-products-menu';
$data     = sarafatto_get_products_menu_data();
$product_label = sarafatto_theme_label( 'Prodotti', 'Products' );
$all_label = sarafatto_theme_label( 'Tutti i prodotti', 'All products' );
?>
<div class="products-menu">
	<div class="products-menu__desktop" id="<?php echo esc_attr( $panel_id . '-desktop' ); ?>" aria-hidden="true" inert>
		<nav class="products-menu__links" aria-label="<?php echo esc_attr( $product_label ); ?>">
			<ul class="products-menu__list">
				<li><a class="products-menu__link products-menu__link--all<?php echo $data['archive_active'] ? ' is-current' : ''; ?>" href="<?php echo esc_url( $data['archive_url'] ); ?>"<?php echo $data['archive_active'] ? ' aria-current="page"' : ''; ?>><span><?php echo esc_html( $all_label ); ?></span><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></a></li>
				<?php if ( $data['news_link'] ) : ?>
					<li><a class="products-menu__link<?php echo $data['news_link']['active'] ? ' is-current' : ''; ?>" href="<?php echo esc_url( $data['news_link']['url'] ); ?>"<?php echo $data['news_link']['active'] ? ' aria-current="page"' : ''; ?>><span><?php echo esc_html( $data['news_link']['title'] ); ?></span><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></a></li>
				<?php endif; ?>
				<?php if ( $data['news_link'] && $data['menu_links'] ) : ?><li class="products-menu__divider" aria-hidden="true"></li><?php endif; ?>
				<?php foreach ( $data['menu_links'] as $menu_link ) : ?>
					<li><a class="products-menu__link<?php echo $menu_link['active'] ? ' is-current' : ''; ?>" href="<?php echo esc_url( $menu_link['url'] ); ?>"<?php echo $menu_link['active'] ? ' aria-current="page"' : ''; ?>><span><?php echo esc_html( $menu_link['title'] ); ?></span><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></a></li>
				<?php endforeach; ?>
			</ul>
		</nav>
		<?php get_template_part( 'template-parts/components/menu-promo', null, array( 'promo' => $data['promo'], 'context' => 'desktop' ) ); ?>
	</div>

	<div class="products-menu__mobile" id="<?php echo esc_attr( $panel_id . '-mobile' ); ?>" aria-hidden="true" hidden inert>
		<header class="products-menu__mobile-header">
			<button class="site-navigation__back products-menu__back" type="button" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Torna al menu principale', 'Back to main menu' ) ); ?>"><span class="icon-[mdi--arrow-left]" aria-hidden="true"></span></button>
			<h2><?php echo esc_html( $product_label ); ?></h2>
		</header>
		<ul class="products-menu__mobile-list" aria-label="<?php echo esc_attr( $product_label ); ?>">
			<li><a class="products-menu__mobile-link products-menu__mobile-link--all<?php echo $data['archive_active'] ? ' is-current' : ''; ?>" href="<?php echo esc_url( $data['archive_url'] ); ?>"<?php echo $data['archive_active'] ? ' aria-current="page"' : ''; ?>><span><?php echo esc_html( $all_label ); ?></span><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></a></li>
			<?php if ( $data['news_link'] ) : ?><li><a class="products-menu__mobile-link<?php echo $data['news_link']['active'] ? ' is-current' : ''; ?>" href="<?php echo esc_url( $data['news_link']['url'] ); ?>"<?php echo $data['news_link']['active'] ? ' aria-current="page"' : ''; ?>><span><?php echo esc_html( $data['news_link']['title'] ); ?></span><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></a></li><?php endif; ?>
			<?php if ( $data['news_link'] && $data['menu_links'] ) : ?><li class="products-menu__mobile-divider" aria-hidden="true"></li><?php endif; ?>
			<?php foreach ( $data['menu_links'] as $menu_link ) : ?>
				<li><a class="products-menu__mobile-link<?php echo $menu_link['active'] ? ' is-current' : ''; ?>" href="<?php echo esc_url( $menu_link['url'] ); ?>"<?php echo $menu_link['active'] ? ' aria-current="page"' : ''; ?>><span><?php echo esc_html( $menu_link['title'] ); ?></span><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></a></li>
			<?php endforeach; ?>
		</ul>
	</div>
</div>
