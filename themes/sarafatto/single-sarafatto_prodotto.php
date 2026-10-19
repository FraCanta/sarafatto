<?php
/** Editorial single template for the Saràfatto product catalog. */
get_header();

while ( have_posts() ) :
	the_post();
	$product_id  = get_the_ID();
	$product_url = get_permalink( $product_id );
	$english     = function_exists( 'sarafatto_get_current_language' ) && 0 === strpos( sarafatto_get_current_language(), 'en' );
	$flags       = function_exists( 'sarafatto_get_product_flags' ) ? sarafatto_get_product_flags( $product_id ) : array( 'is_new' => false, 'is_sold_out' => false, 'personalizable' => false );
	$price       = function_exists( 'sarafatto_format_price' ) && function_exists( 'sarafatto_get_product_price' ) ? sarafatto_format_price( sarafatto_get_product_price( $product_id ) ) : '';
	$excerpt     = trim( (string) get_post_field( 'post_excerpt', $product_id ) );
	$story       = get_post_meta( $product_id, 'sarafatto_story', true );
	$story       = is_string( $story ) ? $story : '';
	$story_title = get_post_meta( $product_id, 'sarafatto_story_title', true );
	$story_title = is_scalar( $story_title ) ? trim( (string) $story_title ) : '';
	$story_image_id = function_exists( 'sarafatto_sanitize_product_image_id' ) ? sarafatto_sanitize_product_image_id( get_post_meta( $product_id, 'sarafatto_story_image', true ) ) : absint( get_post_meta( $product_id, 'sarafatto_story_image', true ) );
	if ( $story_image_id && ! wp_attachment_is_image( $story_image_id ) ) {
		$story_image_id = 0;
	}
	$detail_fields = array(
		'sarafatto_materials' => sarafatto_theme_label( 'Materiali', 'Materials' ),
		'sarafatto_dimensions' => sarafatto_theme_label( 'Dimensioni', 'Dimensions' ),
		'sarafatto_colors' => sarafatto_theme_label( 'Colori', 'Colours' ),
		'sarafatto_variants' => sarafatto_theme_label( 'Varianti', 'Variants' ),
		'sarafatto_customization_details' => sarafatto_theme_label( 'Personalizzazione', 'Personalization' ),
		'sarafatto_care' => sarafatto_theme_label( 'Cura del prodotto', 'Care instructions' ),
	);
	$dummy_values = get_post_meta( $product_id, 'sarafatto_dummy_details', true );
	$dummy_values = is_array( $dummy_values ) ? $dummy_values : array();
	$show_demo_data = function_exists( 'sarafatto_is_dummy_data_environment' ) && sarafatto_is_dummy_data_environment();
	$product_detail_rows = array();
	foreach ( $detail_fields as $meta_key => $label ) {
		$detail_value = get_post_meta( $product_id, $meta_key, true );
		if ( 'sarafatto_customization_details' === $meta_key ) {
			if ( ! is_scalar( $detail_value ) || '' === trim( (string) $detail_value ) ) {
				$detail_value = get_post_meta( $product_id, 'sarafatto_personalization_details', true );
			}
			if ( empty( $flags['personalizable'] ) ) {
				continue;
			}
			if ( ! is_scalar( $detail_value ) || '' === trim( (string) $detail_value ) ) {
				$detail_value = sarafatto_theme_label( 'Sì', 'Yes' );
			}
		}
		if ( ! $show_demo_data && isset( $dummy_values[ $meta_key ] ) && is_scalar( $detail_value ) && (string) $detail_value === (string) $dummy_values[ $meta_key ] ) {
			continue;
		}
		if ( is_scalar( $detail_value ) && '' !== trim( (string) $detail_value ) ) {
			$product_detail_rows[] = array( 'label' => $label, 'value' => (string) $detail_value );
		}
	}
	$handmade_value = get_post_meta( $product_id, 'sarafatto_is_handmade', true );
	$handmade = '1' === (string) $handmade_value && ( $show_demo_data || ! isset( $dummy_values['sarafatto_is_handmade'] ) || (string) $handmade_value !== (string) $dummy_values['sarafatto_is_handmade'] );
	$featured_id = get_post_thumbnail_id( $product_id );
	$gallery_ids = function_exists( 'sarafatto_sanitize_gallery_ids' ) ? sarafatto_sanitize_gallery_ids( get_post_meta( $product_id, 'sarafatto_gallery', true ) ) : array();
	$gallery_ids = array_values( array_unique( array_filter( array_merge( $featured_id ? array( $featured_id ) : array(), $gallery_ids ) ) ) );
	$main_image_id = $gallery_ids ? (int) $gallery_ids[0] : 0;
	$normalize_terms = static function ( $terms ) {
		if ( ! is_array( $terms ) ) {
			return array();
		}
		return array_values( array_filter( $terms, static function ( $term ) {
			return $term instanceof WP_Term && ! is_wp_error( get_term_link( $term ) );
		} ) );
	};
	$categories = $normalize_terms( get_the_terms( $product_id, 'sarafatto_categoria' ) );
	$occasions  = $normalize_terms( get_the_terms( $product_id, 'sarafatto_occasione' ) );
	$gift_ideas = $normalize_terms( get_the_terms( $product_id, 'sarafatto_idea_regalo' ) );
	$taxonomy_groups = array(
		array( 'label' => sarafatto_theme_label( 'Categoria', 'Category' ), 'terms' => $categories ),
		array( 'label' => sarafatto_theme_label( 'Occasione', 'Occasion' ), 'terms' => $occasions ),
		array( 'label' => sarafatto_theme_label( 'Idea regalo', 'Gift idea' ), 'terms' => $gift_ideas ),
	);
	foreach ( $taxonomy_groups as $group ) {
		if ( $group['terms'] ) {
			$product_detail_rows[] = array( 'label' => $group['label'], 'terms' => $group['terms'] );
		}
	}
	$archive_url = function_exists( 'sarafatto_get_products_archive_url' ) ? sarafatto_get_products_archive_url() : get_post_type_archive_link( 'sarafatto_prodotto' );
	$shipping_page = function_exists( 'sarafatto_get_linked_page' ) ? sarafatto_get_linked_page( 'spedizioni' ) : null;
	$shipping_url = $shipping_page instanceof WP_Post ? get_permalink( $shipping_page ) : '';
	$whatsapp_message = $english
		? sprintf( 'Hi Sara, I would like to know about availability and details for: %1$s %2$s', get_the_title( $product_id ), $product_url )
		: sprintf( 'Ciao Sara, vorrei sapere disponibilità e dettagli per: %1$s %2$s', get_the_title( $product_id ), $product_url );
	if ( ! empty( $flags['is_sold_out'] ) ) {
		$whatsapp_message = $english
			? sprintf( 'Hi Sara, this product is sold out. I would like to know if it will be available again: %1$s %2$s', get_the_title( $product_id ), $product_url )
			: sprintf( 'Ciao Sara, questo prodotto risulta esaurito. Vorrei sapere se tornerà disponibile: %1$s %2$s', get_the_title( $product_id ), $product_url );
	}
	$whatsapp_url = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url( $whatsapp_message ) : '';
	$archive_banner_id = function_exists( 'sarafatto_get_product_archive_banner_id' ) ? sarafatto_get_product_archive_banner_id() : 0;
	$related = array();
	$first_category = is_array( $categories ) ? reset( $categories ) : false;
	if ( $first_category instanceof WP_Term ) {
		$related_args = array(
			'post_type'           => 'sarafatto_prodotto',
			'post_status'         => 'publish',
			'posts_per_page'      => 4,
			'post__not_in'        => array( $product_id ),
			'ignore_sticky_posts' => true,
			'tax_query'           => array( array( 'taxonomy' => 'sarafatto_categoria', 'field' => 'term_id', 'terms' => (int) $first_category->term_id ) ), // phpcs:ignore WordPress.DB.SlowDBQuery.slow_db_query_tax_query
		);
		if ( function_exists( 'sarafatto_add_language_to_query_args' ) ) {
			$related_args = sarafatto_add_language_to_query_args( $related_args );
		}
		$related_query = new WP_Query( $related_args );
		$related = $related_query->posts;
		wp_reset_postdata();
	}
	?>
	<main id="main-content" class="site-main product-single" tabindex="-1">
		<div class="container product-single__container">
			<nav class="product-single__breadcrumb" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Percorso di navigazione', 'Breadcrumb' ) ); ?>">
				<a href="<?php echo esc_url( function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Home', 'Home' ) ); ?></a>
				<span aria-hidden="true">›</span>
				<a href="<?php echo esc_url( $archive_url ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Prodotti', 'Products' ) ); ?></a>
				<?php if ( $first_category instanceof WP_Term ) : $category_url = get_term_link( $first_category ); if ( ! is_wp_error( $category_url ) ) : ?>
					<span aria-hidden="true">›</span><a href="<?php echo esc_url( $category_url ); ?>"><?php echo esc_html( $first_category->name ); ?></a>
				<?php endif; endif; ?>
				<span aria-hidden="true">›</span><span aria-current="page"><?php the_title(); ?></span>
			</nav>

			<section class="product-single__main" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Dettagli del prodotto', 'Product details' ) ); ?>">
				<?php $gallery_srcset_limit = static function () { return 1024; }; add_filter( 'max_srcset_image_width', $gallery_srcset_limit, 10, 0 ); ?>
				<div class="product-gallery" data-product-gallery>
					<figure class="product-gallery__stage">
						<?php if ( ! empty( $flags['is_sold_out'] ) ) : ?><span class="product-card__badge product-card__badge--sold-out"><?php echo esc_html( sarafatto_theme_label( 'Esaurito', 'Sold out' ) ); ?></span><?php elseif ( ! empty( $flags['is_new'] ) ) : ?><span class="product-card__badge"><?php echo esc_html( sarafatto_theme_label( 'Novità', 'New' ) ); ?></span><?php endif; ?>
						<?php if ( $main_image_id ) : $main_alt = get_post_meta( $main_image_id, '_wp_attachment_image_alt', true ); if ( '' === trim( (string) $main_alt ) ) { $main_alt = get_the_title( $product_id ); } ?>
							<?php echo wp_get_attachment_image( $main_image_id, 'large', false, array( 'class' => 'product-gallery__image', 'alt' => $main_alt, 'loading' => 'eager', 'fetchpriority' => 'high', 'decoding' => 'async' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated by wp_get_attachment_image(). ?>
						<?php else : ?><div class="product-gallery__placeholder" aria-hidden="true"></div><?php endif; ?>
					</figure>
					<?php if ( count( $gallery_ids ) > 1 ) : ?>
						<div class="product-gallery__thumbs" role="group" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Altre immagini del prodotto', 'More product images' ) ); ?>">
							<?php foreach ( $gallery_ids as $index => $image_id ) : $image_alt = get_post_meta( $image_id, '_wp_attachment_image_alt', true ); if ( '' === trim( (string) $image_alt ) ) { $image_alt = get_the_title( $product_id ); } $image_full = wp_get_attachment_image_src( $image_id, 'large' ); if ( ! $image_full ) { continue; } ?>
								<button class="product-gallery__thumb<?php echo 0 === $index ? ' is-active' : ''; ?>" type="button" data-gallery-src="<?php echo esc_url( $image_full[0] ); ?>" data-gallery-srcset="<?php echo esc_attr( wp_get_attachment_image_srcset( $image_id, 'large' ) ); ?>" data-gallery-sizes="<?php echo esc_attr( wp_get_attachment_image_sizes( $image_id, 'large' ) ); ?>" data-gallery-alt="<?php echo esc_attr( $image_alt ); ?>" aria-label="<?php echo esc_attr( sprintf( sarafatto_theme_label( 'Mostra immagine %d', 'Show image %d' ), $index + 1 ) ); ?>" aria-pressed="<?php echo 0 === $index ? 'true' : 'false'; ?>">
									<?php echo wp_get_attachment_image( $image_id, 'medium', false, array( 'alt' => '', 'loading' => 'lazy', 'decoding' => 'async' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated by wp_get_attachment_image(). ?>
								</button>
							<?php endforeach; ?>
						</div>
					<?php endif; ?>
				</div>
				<?php remove_filter( 'max_srcset_image_width', $gallery_srcset_limit, 10 ); ?>

				<div class="product-single__info">
					<?php if ( ! empty( $flags['is_sold_out'] ) ) : ?><p class="product-single__eyebrow"><?php echo esc_html( sarafatto_theme_label( 'Esaurito', 'Sold out' ) ); ?></p><?php elseif ( ! empty( $flags['is_new'] ) ) : ?><p class="product-single__eyebrow"><?php echo esc_html( sarafatto_theme_label( 'Novità', 'New' ) ); ?></p><?php endif; ?>
					<h1 class="product-single__title"><?php the_title(); ?></h1>
					<?php if ( $price ) : ?><p class="product-single__price"><?php echo esc_html( $price ); ?></p><?php endif; ?>
					<?php if ( $excerpt ) : ?><p class="product-single__excerpt"><?php echo esc_html( $excerpt ); ?></p><?php endif; ?>

					<?php if ( ! empty( $flags['personalizable'] ) || $handmade || ( is_array( $gift_ideas ) && $gift_ideas ) ) : ?>
						<ul class="product-single__features" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Caratteristiche', 'Features' ) ); ?>">
							<?php if ( $handmade ) : ?><li><span class="product-single__feature-icon icon-[cil--eco]" aria-hidden="true"></span><?php echo esc_html( sarafatto_theme_label( 'Realizzato a mano', 'Handmade' ) ); ?></li><?php endif; ?>
							<?php if ( ! empty( $flags['personalizable'] ) ) : ?><li><span class="product-single__feature-icon icon-[mdi--heart-outline]" aria-hidden="true"></span><?php echo esc_html( sarafatto_theme_label( 'Personalizzabile', 'Personalizable' ) ); ?></li><?php endif; ?>
							<?php if ( $gift_ideas ) : ?><li><span class="product-single__feature-icon icon-[mdi--gift-outline]" aria-hidden="true"></span><?php echo esc_html( sarafatto_theme_label( 'Perfetto come idea regalo', 'Perfect as a gift' ) ); ?></li><?php endif; ?>
						</ul>
					<?php endif; ?>

					<?php if ( $whatsapp_url ) : ?>
						<div class="product-single__actions">
						<?php get_template_part( 'template-parts/components/button', null, array( 'label' => empty( $flags['is_sold_out'] ) ? sarafatto_theme_label( 'Chiedi disponibilità su WhatsApp', 'Ask about availability on WhatsApp' ) : sarafatto_theme_label( 'Chiedi se tornerà disponibile', 'Ask if it will be available again' ), 'href' => $whatsapp_url, 'variant' => 'primary', 'size' => 'md', 'icon' => 'whatsapp', 'trailing_icon' => 'arrow-right', 'external' => true, 'class' => empty( $flags['is_sold_out'] ) ? 'product-single__cta' : 'product-single__cta product-single__cta--sold-out' ) ); ?>
						</div>
					<?php endif; ?>

					<div class="product-single__shipping">
						<span class="product-single__shipping-message"><span class="icon-[mdi--truck-outline]" aria-hidden="true"></span><span><?php echo esc_html( sarafatto_theme_label( 'Spedizioni in Italia e in Europa', 'Shipping across Italy and Europe' ) ); ?></span></span>
						<?php if ( $shipping_url ) : ?><a href="<?php echo esc_url( $shipping_url ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Come funziona', 'How it works' ) ); ?><span class="icon-[mdi--arrow-right]" aria-hidden="true"></span></a><?php endif; ?>
					</div>

				<?php if ( $product_detail_rows ) : ?>
						<section class="product-single__details" aria-labelledby="product-details-title">
							<h2 id="product-details-title"><?php echo esc_html( sarafatto_theme_label( 'Dettagli prodotto', 'Product details' ) ); ?></h2>
							<div class="product-single__detail-list">
								<?php foreach ( $product_detail_rows as $row ) : ?><div class="product-single__detail-row"><span><?php echo esc_html( $row['label'] ); ?></span><span class="product-single__detail-value"><?php if ( ! empty( $row['terms'] ) ) : foreach ( $row['terms'] as $term_index => $term ) : $term_url = get_term_link( $term ); if ( is_wp_error( $term_url ) ) { continue; } ?><?php if ( $term_index > 0 ) : ?><span aria-hidden="true">, </span><?php endif; ?><a href="<?php echo esc_url( $term_url ); ?>"><?php echo esc_html( $term->name ); ?></a><?php endforeach; ?><?php else : ?><?php echo nl2br( esc_html( $row['value'] ?? '' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Escaped text with intentional line breaks. ?><?php endif; ?></span></div><?php endforeach; ?>
							</div>
							<div class="product-single__detail-mobile-list">
								<?php foreach ( $product_detail_rows as $row ) : ?><details class="product-single__detail-row"><summary><?php echo esc_html( $row['label'] ); ?></summary><div class="product-single__detail-mobile-value"><?php if ( ! empty( $row['terms'] ) ) : foreach ( $row['terms'] as $term_index => $term ) : $term_url = get_term_link( $term ); if ( is_wp_error( $term_url ) ) { continue; } ?><?php if ( $term_index > 0 ) : ?><span aria-hidden="true">, </span><?php endif; ?><a href="<?php echo esc_url( $term_url ); ?>"><?php echo esc_html( $term->name ); ?></a><?php endforeach; ?><?php else : ?><?php echo nl2br( esc_html( $row['value'] ?? '' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Escaped text with intentional line breaks. ?><?php endif; ?></div></details><?php endforeach; ?>
							</div>
						</section>
					<?php endif; ?>
				</div>
			</section>

			<?php if ( '' !== trim( wp_strip_all_tags( (string) $story ) ) ) : ?>
				<section class="product-single__story<?php echo $story_image_id ? '' : ' product-single__story--text-only'; ?>"<?php echo $story_title ? ' aria-labelledby="product-story-title"' : ' aria-label="' . esc_attr( sarafatto_theme_label( 'Approfondimento', 'More about this product' ) ) . '"'; ?>>
					<?php if ( $story_image_id ) : $story_image_alt = get_post_meta( $story_image_id, '_wp_attachment_image_alt', true ); if ( '' === trim( (string) $story_image_alt ) ) { $story_image_alt = $story_title ? $story_title : get_the_title( $product_id ); } ?>
						<figure class="product-single__story-media"><?php echo wp_get_attachment_image( $story_image_id, 'large', false, array( 'alt' => $story_image_alt, 'loading' => 'lazy', 'decoding' => 'async' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated by wp_get_attachment_image(). ?></figure>
					<?php endif; ?>
					<div class="product-single__story-content"><?php if ( $story_title ) : ?><h2 id="product-story-title"><?php echo esc_html( $story_title ); ?></h2><?php endif; ?><?php echo apply_filters( 'the_content', $story ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- WordPress content filters handle allowed editorial markup. ?></div>
				</section>
			<?php endif; ?>

			<?php if ( $related ) : ?><section class="product-single__related" aria-labelledby="product-related-title">
				<h2 id="product-related-title" class="product-single__section-title"><?php echo esc_html( sarafatto_theme_label( 'Potrebbero piacerti anche', 'You might also like' ) ); ?></h2>
				<ul class="product-single__related-grid">
					<?php foreach ( $related as $related_product ) : $related_id = $related_product->ID; $related_flags = function_exists( 'sarafatto_get_product_flags' ) ? sarafatto_get_product_flags( $related_id ) : array( 'is_new' => false, 'is_sold_out' => false ); $related_price = function_exists( 'sarafatto_format_price' ) && function_exists( 'sarafatto_get_product_price' ) ? sarafatto_format_price( sarafatto_get_product_price( $related_id ) ) : ''; ?>
						<li class="product-card"><a class="product-card__link" href="<?php echo esc_url( get_permalink( $related_id ) ); ?>"><span class="product-card__media">
							<?php if ( has_post_thumbnail( $related_id ) ) : $related_image_id = get_post_thumbnail_id( $related_id ); $related_alt = get_post_meta( $related_image_id, '_wp_attachment_image_alt', true ); if ( '' === trim( (string) $related_alt ) ) { $related_alt = get_the_title( $related_id ); } echo wp_get_attachment_image( $related_image_id, 'large', false, array( 'class' => 'product-card__image', 'alt' => $related_alt, 'loading' => 'lazy', 'decoding' => 'async' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated by wp_get_attachment_image(). ?><?php else : ?><span class="product-card__placeholder" aria-hidden="true"></span><?php endif; ?>
							<?php if ( ! empty( $related_flags['is_sold_out'] ) ) : ?><span class="product-card__badge product-card__badge--sold-out"><?php echo esc_html( sarafatto_theme_label( 'Esaurito', 'Sold out' ) ); ?></span><?php elseif ( ! empty( $related_flags['is_new'] ) ) : ?><span class="product-card__badge"><?php echo esc_html( sarafatto_theme_label( 'Novità', 'New' ) ); ?></span><?php endif; ?>
						</span><span class="product-card__details"><span class="product-card__name"><?php echo esc_html( get_the_title( $related_id ) ); ?></span><?php if ( $related_price ) : ?><span class="product-card__price"><?php echo esc_html( $related_price ); ?></span><?php endif; ?></span></a></li>
					<?php endforeach; ?>
				</ul>
			</section><?php endif; ?>
		</div>

		<?php if ( $archive_banner_id ) : ?>
			<section class="product-archive-cta" aria-labelledby="product-archive-cta-title">
				<figure class="product-archive-cta__media"><?php echo wp_get_attachment_image( $archive_banner_id, 'large', false, array( 'class' => 'product-archive-cta__image', 'alt' => sarafatto_theme_label( 'Una donna con un post-it giallo davanti all’occhio', 'A woman with a yellow note covering one eye' ), 'loading' => 'lazy', 'decoding' => 'async' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated by wp_get_attachment_image(). ?></figure>
				<div class="product-archive-cta__content"><h2 id="product-archive-cta-title"><?php echo esc_html( sarafatto_theme_label( 'Scrivimi, posso aiutarti.', 'Message me, I can help.' ) ); ?></h2><p><?php echo esc_html( $english ? 'Are you looking for something in particular or would you like to create something special, made just for you? Tell me your idea!' : 'Cerchi un oggetto in particolare o vuoi realizzare qualcosa di speciale, anche su misura? Raccontami la tua idea!' ); ?></p>
					<?php $banner_message = $english ? 'Hi Sara, I have a question about your products.' : 'Ciao Sara, vorrei chiederti un’informazione sui tuoi prodotti.'; $banner_whatsapp = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url( $banner_message ) : ''; if ( $banner_whatsapp ) { get_template_part( 'template-parts/components/button', null, array( 'label' => sarafatto_theme_label( 'Scrivimi su WhatsApp', 'Message me on WhatsApp' ), 'href' => $banner_whatsapp, 'variant' => 'primary', 'size' => 'md', 'icon' => 'whatsapp', 'external' => true ) ); } ?>
				</div>
			</section>
		<?php endif; ?>
	</main>
	<?php
endwhile;
get_footer();
