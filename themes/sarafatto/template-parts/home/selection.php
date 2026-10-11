<?php
/** Home selection story: Sara's personal point of view. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$shop_url = '';
$shop_page = function_exists( 'sarafatto_get_linked_page' ) ? sarafatto_get_linked_page( 'negozio' ) : null;
if ( $shop_page instanceof WP_Post ) {
	$shop_url = get_permalink( $shop_page );
}

if ( ! $shop_url ) {
	$locations = get_nav_menu_locations();
	$menu_id   = isset( $locations['primary'] ) ? absint( $locations['primary'] ) : 0;
	$items     = $menu_id ? wp_get_nav_menu_items( $menu_id ) : array();
	$items     = is_array( $items ) ? $items : array();
	$shop_label = sarafatto_theme_label( 'Il negozio', 'Shop' );

	foreach ( $items as $item ) {
		if ( isset( $item->title, $item->url ) && sanitize_title( $item->title ) === sanitize_title( $shop_label ) ) {
			$shop_url = $item->url;
			break;
		}
	}
}

$image_url = get_theme_file_uri( '/assets/images/home-selection-eye-note.png' );
?>
<section class="home-selection" aria-labelledby="home-selection-title">
	<div class="home-selection__inner">
		<div class="home-selection__content">
			<h2 class="home-selection__title" id="home-selection-title">
				<span><?php echo esc_html( sarafatto_theme_label( 'Una selezione', 'A selection' ) ); ?></span>
				<span><?php echo esc_html( sarafatto_theme_label( 'che ha un senso', 'that makes sense' ) ); ?></span>
				<span><?php echo esc_html( sarafatto_theme_label( '(anche quando', '(even when' ) ); ?></span>
				<span><?php echo esc_html( sarafatto_theme_label( 'non c’entra niente).', 'it makes no sense).' ) ); ?></span>
			</h2>
			<p class="home-selection__copy"><?php echo esc_html( sarafatto_theme_label( 'Ogni cosa che trovi da SaràFatto passa prima da una scelta precisa. Cerco oggetti che abbiano qualcosa da dire: belli, originali, ironici o semplicemente impossibili da ignorare. Anche quando sono completamente diversi tra loro, devono riuscire a stare bene nello stesso mondo.', 'Every item you find at SaràFatto starts with a deliberate choice. I look for objects with something to say: beautiful, original, witty, or simply impossible to ignore. Even when they are completely different, they need to belong in the same world.' ) ); ?></p>
			<?php if ( $shop_url ) : ?>
				<div class="home-selection__cta">
					<?php
					get_template_part(
						'template-parts/components/button',
						null,
						array(
							'label'   => sarafatto_theme_label( 'Scopri come scelgo', 'Discover how I choose' ),
							'href'    => $shop_url,
							'variant' => 'secondary',
							'size'    => 'md',
							'icon'    => 'arrow-up-right',
							'icon_position' => 'after',
							'external' => false,
							'class'   => 'home-selection__button',
						)
					);
					?>
				</div>
			<?php endif; ?>
		</div>

		<figure class="home-selection__media">
			<img
				class="home-selection__image"
				src="<?php echo esc_url( $image_url ); ?>"
				alt="<?php echo esc_attr( sarafatto_theme_label( 'Primo piano in bianco e nero di un occhio, accanto a un post-it giallo con la scritta «Come finiscono queste cose qui dentro?»', 'Black-and-white close-up of an eye beside a yellow note reading “Where do these things end up?”' ) ); ?>"
				width="1448"
				height="1080"
				loading="lazy"
				decoding="async"
			>
		</figure>
	</div>
</section>
