<?php
/** Featured product collection; uses the shared product card. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args = isset( $args ) && is_array( $args ) ? $args : array();
$products = isset( $args['products'] ) && is_array( $args['products'] ) ? $args['products'] : array();
if ( ! $products ) { return; }
$archive_url = function_exists( 'sarafatto_get_products_archive_url' ) ? sarafatto_get_products_archive_url() : get_post_type_archive_link( 'sarafatto_prodotto' );
?>
<section class="home-featured" aria-labelledby="home-featured-title">
	<?php get_template_part( 'template-parts/home/ribbon' ); ?>
	<div class="home-container">
		<header class="home-featured__intro">
			<div class="home-featured__text">
				<h2 class="home-section-title" id="home-featured-title"><?php echo esc_html( sarafatto_theme_label( 'I più amati secondo voi', 'Most loved by you' ) ); ?></h2>
				<p class="home-featured__copy"><?php echo esc_html( sarafatto_theme_label( 'Oggetti scelti da Sara e amati da chi li ha portati a casa.', 'Objects picked by Sara and loved by the people who brought them home.' ) ); ?></p>
			</div>
		</header>
		<ul class="product-grid home-featured__list">
			<?php foreach ( $products as $product ) : ?>
				<?php $GLOBALS['post'] = $product; setup_postdata( $product ); ?>
				<?php get_template_part( 'template-parts/products/product-card', null, array( 'use_gallery_fallback' => true ) ); ?>
			<?php endforeach; ?>
		</ul>
		<?php wp_reset_postdata(); ?>
		<?php if ( $archive_url ) : ?>
			<div class="home-featured__footer">
				<?php
				get_template_part( 'template-parts/components/button', null, array(
					'label' => sarafatto_theme_label( 'Scopri tutti', 'Discover all' ),
					'href' => $archive_url,
					'variant' => 'secondary',
					'size' => 'sm',
					'icon' => 'arrow-right',
					'icon_position' => 'after',
					'class' => 'home-featured__button',
				) );
				?>
			</div>
		<?php endif; ?>
	</div>
</section>
