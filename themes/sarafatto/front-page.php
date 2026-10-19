<?php
/** Front page: render the theme-managed Hero independently from page content. */
get_header();
$home_categories = sarafatto_get_home_categories( 4 );
$home_featured_products = sarafatto_get_home_product_selection( 'sarafatto_is_featured', 6 );
$home_new_products = sarafatto_get_home_product_selection( 'sarafatto_is_new', 4 );
$home_gift_ideas = function_exists( 'sarafatto_get_home_gift_ideas' ) ? sarafatto_get_home_gift_ideas( 2 ) : array();
?>
<main id="main-content" class="site-main site-main--home" tabindex="-1">
	<?php echo sarafatto_render_home_hero(); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
	<?php get_template_part( 'template-parts/home/service-strip' ); ?>
	<?php get_template_part( 'template-parts/home/worlds' ); ?>
	<?php get_template_part( 'template-parts/home/personalized' ); ?>
	<?php get_template_part( 'template-parts/home/choose-category', null, array( 'categories' => $home_categories ) ); ?>
	<?php get_template_part( 'template-parts/home/discoveries', null, array( 'products' => $home_featured_products ) ); ?>
	<?php get_template_part( 'template-parts/home/seasonal-feature' ); ?>
	<?php get_template_part( 'template-parts/home/gift-ideas', null, array( 'ideas' => $home_gift_ideas ) ); ?>
	<?php if ( count( $home_new_products ) >= 4 ) : ?>
		<?php get_template_part( 'template-parts/home/new-products', null, array( 'products' => $home_new_products ) ); ?>
	<?php endif; ?>
	<?php get_template_part( 'template-parts/home/shipping-banner' ); ?>
</main>
<?php get_footer();
