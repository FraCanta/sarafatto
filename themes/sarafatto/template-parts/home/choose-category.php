<?php
/** Compact icon links to the product category archive terms. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$args = isset( $args ) && is_array( $args ) ? $args : array();
$categories = isset( $args['categories'] ) && is_array( $args['categories'] ) ? $args['categories'] : array();
if ( ! $categories ) { return; }
?>
<section class="home-choose-category" aria-labelledby="home-choose-category-title">
	<div class="home-container">
		<p class="home-section-eyebrow"><?php echo esc_html( sarafatto_theme_label( 'Scegli la tua categoria', 'Choose your category' ) ); ?></p>
		<h2 class="home-section-title" id="home-choose-category-title"><?php echo esc_html( sarafatto_theme_label( 'Le cose belle, per come le cerchi.', 'Good things, the way you look for them.' ) ); ?></h2>
		<ul class="home-choose-category__list home-choose-category__list--count-<?php echo esc_attr( count( $categories ) ); ?>">
			<?php foreach ( $categories as $category ) : ?>
				<?php $term = $category['term']; ?>
				<?php
				$icon_by_slug = array(
					'accessori'      => 'icon-[mdi--shopping-outline]',
					'accessories'    => 'icon-[mdi--shopping-outline]',
					'casa'           => 'icon-[mdi--home-outline]',
					'home'           => 'icon-[mdi--home-outline]',
					'bijoux'         => 'icon-[mdi--creation-outline]',
					'jewellery'      => 'icon-[mdi--creation-outline]',
					'jewelry'        => 'icon-[mdi--creation-outline]',
					'abbigliamento'  => 'icon-[mdi--tshirt-crew-outline]',
					'clothing'       => 'icon-[mdi--tshirt-crew-outline]',
					'apparel'        => 'icon-[mdi--tshirt-crew-outline]',
				);
				$category_icon = isset( $icon_by_slug[ $term->slug ] ) ? $icon_by_slug[ $term->slug ] : 'icon-[mdi--shape-outline]';
				?>
				<li class="home-choose-category__item">
					<a href="<?php echo esc_url( $category['url'] ); ?>">
						<span class="home-choose-category__icon <?php echo esc_attr( $category_icon ); ?>" aria-hidden="true"></span>
						<span class="home-choose-category__label"><?php echo esc_html( $term->name ); ?></span>
						<span class="home-choose-category__arrow" aria-hidden="true">↗</span>
					</a>
				</li>
			<?php endforeach; ?>
		</ul>
	</div>
</section>
