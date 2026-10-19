<?php
/** Dynamic landing page for current-language gift ideas. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$gift_terms = function_exists( 'sarafatto_get_product_archive_terms' )
	? sarafatto_get_product_archive_terms( 'sarafatto_idea_regalo' )
	: get_terms(
		array(
			'taxonomy'   => 'sarafatto_idea_regalo',
			'hide_empty' => true,
			'orderby'    => 'name',
			'order'      => 'ASC',
		)
	);
if ( is_wp_error( $gift_terms ) || ! is_array( $gift_terms ) ) {
	$gift_terms = array();
}

$gift_sections = array();
foreach ( $gift_terms as $gift_term ) {
	if ( ! $gift_term instanceof WP_Term ) {
		continue;
	}

	$product_query_args = array(
		'post_type'              => 'sarafatto_prodotto',
		'post_status'            => 'publish',
		'posts_per_page'         => 4,
		'no_found_rows'          => true,
		'ignore_sticky_posts'    => true,
		'update_post_meta_cache' => true,
		'update_post_term_cache' => false,
		'orderby'                => 'date',
		'order'                  => 'DESC',
		'tax_query'              => array(
			array(
				'taxonomy'         => 'sarafatto_idea_regalo',
				'field'            => 'term_id',
				'terms'            => $gift_term->term_id,
				'include_children' => false,
			),
		),
	);
	if ( function_exists( 'sarafatto_add_language_to_query_args' ) ) {
		$product_query_args = sarafatto_add_language_to_query_args( $product_query_args );
	}
	$products = new WP_Query( $product_query_args );

	if ( ! $products->have_posts() ) {
		wp_reset_postdata();
		continue;
	}

	$gift_sections[] = array(
		'term'     => $gift_term,
		'products' => $products,
	);
}

$products_url = function_exists( 'sarafatto_get_products_archive_url' ) ? sarafatto_get_products_archive_url() : get_post_type_archive_link( 'sarafatto_prodotto' );
$whatsapp_url = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url( sarafatto_theme_label( 'Ciao Sara, cerco un’idea regalo.', 'Hi Sara, I’m looking for a gift idea.' ) ) : '';
?>
<main id="main-content" class="site-main gift-ideas" tabindex="-1">
	<div class="container gift-ideas__container">
		<?php while ( have_posts() ) : the_post(); ?>
			<header class="gift-ideas__intro">
				<nav class="product-archive__breadcrumb" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Percorso di navigazione', 'Breadcrumb' ) ); ?>">
					<a href="<?php echo esc_url( function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Home', 'Home' ) ); ?></a>
					<span aria-hidden="true">›</span>
					<span aria-current="page"><?php echo esc_html( get_the_title() ); ?></span>
				</nav>
				<h1 class="gift-ideas__title"><span class="editorial-underline editorial-underline--02"><?php echo esc_html( get_the_title() ); ?></span></h1>
				<?php if ( trim( wp_strip_all_tags( get_the_content() ) ) ) : ?>
					<div class="gift-ideas__description"><?php the_content(); ?></div>
				<?php endif; ?>
			</header>
		<?php endwhile; ?>

		<?php if ( $gift_sections ) : ?>
			<nav class="gift-ideas__quick-nav" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Navigazione rapida idee regalo', 'Quick navigation for gift ideas' ) ); ?>">
				<?php foreach ( $gift_sections as $section ) : ?>
					<?php $term_title = function_exists( 'sarafatto_get_gift_idea_display_title' ) ? sarafatto_get_gift_idea_display_title( $section['term']->term_id ) : $section['term']->name; ?>
					<a href="#gift-idea-<?php echo esc_attr( $section['term']->term_id ); ?>"><?php echo esc_html( $term_title ); ?></a>
				<?php endforeach; ?>
			</nav>

			<div class="gift-ideas__sections">
				<?php foreach ( $gift_sections as $section ) : ?>
					<?php
					$term         = $section['term'];
					$term_title   = function_exists( 'sarafatto_get_gift_idea_display_title' ) ? sarafatto_get_gift_idea_display_title( $term->term_id ) : $term->name;
					$term_intro   = get_term_meta( $term->term_id, 'sarafatto_idea_regalo_intro', true );
					$term_body    = get_term_meta( $term->term_id, 'sarafatto_idea_regalo_description', true );
					$term_image   = function_exists( 'sarafatto_get_gift_idea_image_id' ) ? sarafatto_get_gift_idea_image_id( $term->term_id ) : 0;
					$term_icon    = function_exists( 'sarafatto_get_gift_idea_icon' ) ? sarafatto_get_gift_idea_icon( $term->term_id ) : '';
					if ( ! is_string( $term_intro ) || '' === trim( $term_intro ) ) {
						$term_intro = term_description( $term->term_id, 'sarafatto_idea_regalo' );
					}
					?>
					<section class="gift-ideas__section" id="gift-idea-<?php echo esc_attr( $term->term_id ); ?>" aria-labelledby="gift-idea-title-<?php echo esc_attr( $term->term_id ); ?>">
						<header class="gift-ideas__section-header<?php echo ( $term_image || $term_icon ) ? ' has-media' : ''; ?>">
							<?php if ( $term_image ) : ?>
								<?php echo wp_get_attachment_image( $term_image, 'large', false, array( 'class' => 'gift-ideas__term-image', 'alt' => $term_title, 'loading' => 'lazy', 'decoding' => 'async' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated by wp_get_attachment_image(). ?>
							<?php elseif ( $term_icon && function_exists( 'sarafatto_get_term_icon_markup' ) ) : ?>
								<?php echo sarafatto_get_term_icon_markup( $term_icon, 'gift-ideas__term-icon' ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated from the approved editorial icon sprite. ?>
							<?php endif; ?>
							<div class="gift-ideas__section-heading">
								<h2 id="gift-idea-title-<?php echo esc_attr( $term->term_id ); ?>"><?php echo esc_html( $term_title ); ?></h2>
								<?php if ( $term_intro ) : ?><div class="gift-ideas__term-intro"><?php echo wp_kses_post( $term_intro ); ?></div><?php endif; ?>
							</div>
						</header>

						<ul class="product-grid" aria-label="<?php echo esc_attr( sprintf( sarafatto_theme_label( 'Prodotti: %s', 'Products: %s' ), $term_title ) ); ?>">
							<?php foreach ( $section['products']->posts as $product_post ) : ?>
								<?php $GLOBALS['post'] = $product_post; setup_postdata( $product_post ); ?>
								<?php get_template_part( 'template-parts/products/product-card' ); ?>
							<?php endforeach; ?>
						</ul>
						<?php wp_reset_postdata(); ?>

						<?php if ( is_string( $term_body ) && '' !== trim( $term_body ) ) : ?>
							<div class="gift-ideas__term-description"><?php echo wp_kses_post( $term_body ); ?></div>
						<?php endif; ?>
					</section>
				<?php endforeach; ?>
			</div>
		<?php else : ?>
			<section class="gift-ideas__empty" aria-labelledby="gift-ideas-empty-title">
				<h2 id="gift-ideas-empty-title"><?php echo esc_html( sarafatto_theme_label( 'Sto ancora mettendo insieme le idee giuste.', 'I’m still putting together the right ideas.' ) ); ?></h2>
				<?php if ( $products_url ) : ?>
					<?php get_template_part( 'template-parts/components/button', null, array( 'label' => sarafatto_theme_label( 'Scopri tutti i prodotti', 'Discover all products' ), 'href' => $products_url, 'variant' => 'primary', 'size' => 'md', 'trailing_icon' => 'arrow-right', 'class' => 'gift-ideas__empty-cta' ) ); ?>
				<?php endif; ?>
			</section>
		<?php endif; ?>
	</div>

	<?php if ( $whatsapp_url ) : ?>
		<section class="gift-ideas__contact" aria-labelledby="gift-ideas-contact-title">
			<div class="container gift-ideas__contact-inner">
				<div>
					<h2 id="gift-ideas-contact-title"><?php echo esc_html( sarafatto_theme_label( 'Non trovi il regalo giusto?', 'Can’t find the right gift?' ) ); ?></h2>
					<p><?php echo esc_html( sarafatto_theme_label( 'Scrivimi, ti aiuto a trovare l’idea giusta.', 'Message me and I’ll help you find the right idea.' ) ); ?></p>
				</div>
				<?php get_template_part( 'template-parts/components/button', null, array( 'label' => sarafatto_theme_label( 'Scrivimi su WhatsApp', 'Message me on WhatsApp' ), 'href' => $whatsapp_url, 'variant' => 'primary', 'size' => 'md', 'icon' => 'whatsapp', 'external' => true ) ); ?>
			</div>
		</section>
	<?php endif; ?>
</main>
