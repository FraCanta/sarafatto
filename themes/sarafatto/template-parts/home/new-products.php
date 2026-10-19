<?php
/** Home selection using the existing sarafatto_is_new product flag. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args = isset( $args ) && is_array( $args ) ? $args : array();
$products = isset( $args['products'] ) && is_array( $args['products'] ) ? $args['products'] : array();
if ( ! $products ) { return; }
?>
<section class="home-product-selection home-product-selection--new" aria-labelledby="home-new-products-title">
	<div class="home-container">
		<header class="home-product-selection__intro">
			<div>
				<p class="home-section-eyebrow"><?php echo esc_html( sarafatto_theme_label( 'Appena arrivati', 'Just arrived' ) ); ?></p>
				<h2 class="home-section-title" id="home-new-products-title"><?php echo esc_html( sarafatto_theme_label( 'Novità', 'New arrivals' ) ); ?></h2>
			</div>
		</header>
		<ul class="product-grid">
			<?php foreach ( $products as $product ) : ?>
				<?php $GLOBALS['post'] = $product; setup_postdata( $product ); ?>
				<?php get_template_part( 'template-parts/products/product-card', null, array( 'use_gallery_fallback' => true ) ); ?>
			<?php endforeach; ?>
		</ul>
		<?php wp_reset_postdata(); ?>
	</div>
</section>
