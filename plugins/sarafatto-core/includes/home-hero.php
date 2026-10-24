<?php
/** Theme-managed Home Hero, rendered outside the page editor. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Keep the three scene definitions together so they can later move to settings. */
function sarafatto_home_hero_slides() {
	$products_url = function_exists( 'sarafatto_get_products_archive_url' )
		? sarafatto_get_products_archive_url()
		: get_post_type_archive_link( 'sarafatto_prodotto' );
	$gift_page   = function_exists( 'sarafatto_get_linked_page' ) ? sarafatto_get_linked_page( 'idee_regalo' ) : null;
	$custom_page = function_exists( 'sarafatto_get_linked_page' ) ? sarafatto_get_linked_page( 'personalizzati' ) : null;
	$home_url    = function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' );

	return array(
		array(
			'id'           => 'products',
			'title'        => 'SARÀ FATTO',
			'copy'         => sarafatto_theme_label( 'Frasi, oggetti e idee con carattere.', 'Phrases, objects and ideas with character.' ),
			'ctaLabel'     => sarafatto_theme_label( 'Scopri i prodotti', 'Discover our products' ),
			'ctaUrl'       => $products_url ? $products_url : $home_url,
			'background'   => '#F3ECE4',
			'titleColor'   => '#1A1A1A',
			'accentColor'  => '#FFC942',
			'visual'       => get_theme_file_uri( '/assets/images/sara-fatto-slide.png' ),
			'icon'         => 'icon-[mdi--shopping-outline]',
			'selectorLabel'=> sarafatto_theme_label( 'Mostra Sarà Fatto', 'Show Sarà Fatto' ),
		),
		array(
			'id'           => 'gift',
			'title'        => sarafatto_theme_label( 'IDEE REGALO', 'GIFT IDEAS' ),
			'copy'         => sarafatto_theme_label( 'Per quando vuoi regalare qualcosa che dica davvero qualcosa.', 'For when you want to give a gift that really says something.' ),
			'ctaLabel'     => sarafatto_theme_label( 'Scopri le idee regalo', 'Discover gift ideas' ),
			'ctaUrl'       => $gift_page instanceof WP_Post ? get_permalink( $gift_page ) : $home_url,
			'background'   => '#F6E3E8',
			'titleColor'   => '#E91E8E',
			'accentColor'  => '#E91E8E',
			'visual'       => get_theme_file_uri( '/assets/images/idee-regalo-slide.png' ),
			'icon'         => 'icon-[mdi--gift-outline]',
			'selectorLabel'=> sarafatto_theme_label( 'Mostra le idee regalo', 'Show gift ideas' ),
		),
		array(
			'id'           => 'custom',
			'title'        => sarafatto_theme_label( 'PERSONALIZZATI', 'PERSONALISED' ),
			'copy'         => sarafatto_theme_label( 'Una frase o un’idea. La trasformiamo in qualcosa di tuo.', 'A phrase or an idea. We turn it into something of your own.' ),
			'ctaLabel'     => sarafatto_theme_label( 'Scopri i personalizzati', 'Discover personalised gifts' ),
			'ctaUrl'       => $custom_page instanceof WP_Post ? get_permalink( $custom_page ) : $home_url,
			'background'   => '#DCEFED',
			'titleColor'   => '#00A79D',
			'accentColor'  => '#00A79D',
			'visual'       => get_theme_file_uri( '/assets/images/personalizzati-slide.png' ),
			'icon'         => 'icon-[mdi--creation-outline]',
			'selectorLabel'=> sarafatto_theme_label( 'Mostra i personalizzati', 'Show personalised gifts' ),
		),
	);
}

/** Build a responsive srcset for an optimized Hero scene format. */
function sarafatto_home_hero_responsive_srcset( $visual, $format ) {
	if ( ! in_array( $format, array( 'avif', 'webp' ), true ) ) {
		return '';
	}

	$base   = preg_replace( '/\.png$/i', '', $visual );
	$widths = array( 480, 768, 1122 );
	$srcset = array();

	foreach ( $widths as $width ) {
		$srcset[] = $base . '-' . $width . '.' . $format . ' ' . $width . 'w';
	}

	return implode( ', ', $srcset );
}

/** Render the scene-switching Home Hero. */
function sarafatto_render_home_hero() {
	$slides     = sarafatto_home_hero_slides();
	$first      = $slides[0];
	$heading    = sarafatto_theme_label( 'SaràFatto — prodotti, idee regalo e personalizzati', 'SaràFatto — products, gift ideas and personalised creations' );
	$group_label = sarafatto_theme_label( 'Seleziona una sezione', 'Choose a section' );
	$image_sizes = '(max-width: 47.999rem) calc(86vw - 22px), (max-width: 63.999rem) calc(48vw - 21px), min(46vw, 44rem)';
	$markup     = '<div class="home-hero-scroll-frame"><section class="home-hero hero-slider" data-active-slide="products" aria-labelledby="home-hero-title">';
	$markup    .= '<h1 id="home-hero-title" class="screen-reader-text">' . esc_html( $heading ) . '</h1>';
	$markup    .= '<div class="hero-slider__stage" aria-hidden="true"><p class="hero-slider__title" data-hero-title>' . esc_html( $first['title'] ) . '</p><picture class="hero-slide-visual" data-hero-visual>';
	$markup    .= '<source type="image/avif" srcset="' . esc_attr( sarafatto_home_hero_responsive_srcset( $first['visual'], 'avif' ) ) . '" sizes="' . esc_attr( $image_sizes ) . '" />';
	$markup    .= '<source type="image/webp" srcset="' . esc_attr( sarafatto_home_hero_responsive_srcset( $first['visual'], 'webp' ) ) . '" sizes="' . esc_attr( $image_sizes ) . '" />';
	$markup    .= '<img class="hero-slide-visual__image" src="' . esc_url( $first['visual'] ) . '" alt="" width="1122" height="1402" loading="eager" fetchpriority="high" decoding="async" />';
	$markup    .= '</picture></div>';
	$markup    .= '<div class="hero-slider__footer"><a class="hero-slider__cta" data-hero-cta href="' . esc_url( $first['ctaUrl'] ) . '"><span class="hero-slider__cta-label" data-hero-cta-label>' . esc_html( $first['ctaLabel'] ) . '</span><span class="hero-slider__cta-arrow icon-[mdi--arrow-right]" aria-hidden="true"></span></a>';
	$markup    .= '<div class="hero-slider__support"><p class="hero-slider__copy" id="hero-slider-copy" data-hero-copy aria-live="polite" aria-atomic="true">' . esc_html( $first['copy'] ) . '</p><div class="hero-slider__selector" role="group" aria-label="' . esc_attr( $group_label ) . '">';

	foreach ( $slides as $index => $slide ) {
		$active = 0 === $index;
		$markup .= '<button class="hero-slider__selector-button' . ( $active ? ' is-active' : '' ) . '" type="button" data-hero-slide="' . esc_attr( $slide['id'] ) . '" data-title="' . esc_attr( $slide['title'] ) . '" data-copy="' . esc_attr( $slide['copy'] ) . '" data-cta-label="' . esc_attr( $slide['ctaLabel'] ) . '" data-cta-url="' . esc_url( $slide['ctaUrl'] ) . '" data-background="' . esc_attr( $slide['background'] ) . '" data-title-color="' . esc_attr( $slide['titleColor'] ) . '" data-accent="' . esc_attr( $slide['accentColor'] ) . '" data-visual="' . esc_attr( $slide['visual'] ) . '" data-visual-avif-srcset="' . esc_attr( sarafatto_home_hero_responsive_srcset( $slide['visual'], 'avif' ) ) . '" data-visual-webp-srcset="' . esc_attr( sarafatto_home_hero_responsive_srcset( $slide['visual'], 'webp' ) ) . '" aria-label="' . esc_attr( $slide['selectorLabel'] ) . '" aria-pressed="' . ( $active ? 'true' : 'false' ) . '"><span class="' . esc_attr( $slide['icon'] ) . '" aria-hidden="true"></span></button>';
	}

	$markup .= '</div></div></div></section></div>';
	return $markup;
}
