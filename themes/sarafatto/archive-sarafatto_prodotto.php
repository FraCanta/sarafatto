<?php
/** Editorial archive for the Saràfatto product catalog. */
get_header();

$archive_url  = function_exists( 'sarafatto_get_products_archive_url' ) ? sarafatto_get_products_archive_url() : get_post_type_archive_link( 'sarafatto_prodotto' );
$categories   = function_exists( 'sarafatto_get_product_archive_terms' ) ? sarafatto_get_product_archive_terms( 'sarafatto_categoria' ) : array();
$gift_ideas   = function_exists( 'sarafatto_get_product_archive_terms' ) ? sarafatto_get_product_archive_terms( 'sarafatto_idea_regalo' ) : array();
$selected_cat = function_exists( 'sarafatto_get_archive_filter_term' ) ? sarafatto_get_archive_filter_term( 'categoria', 'sarafatto_categoria' ) : null;
$selected_gift = function_exists( 'sarafatto_get_archive_filter_term' ) ? sarafatto_get_archive_filter_term( 'idea', 'sarafatto_idea_regalo' ) : null;
$personalizable = isset( $_GET['personalizzabili'] ) && '1' === sanitize_text_field( wp_unslash( $_GET['personalizzabili'] ) ); // phpcs:ignore WordPress.Security.NonceVerification.Recommended
$all_filters_active = $selected_cat instanceof WP_Term || $selected_gift instanceof WP_Term || $personalizable;
$sort = isset( $_GET['ordina'] ) && is_scalar( $_GET['ordina'] ) ? sanitize_key( wp_unslash( $_GET['ordina'] ) ) : 'recenti'; // phpcs:ignore WordPress.Security.NonceVerification.Recommended
$sort_labels = array(
	'recenti'              => sarafatto_theme_label( 'Più recenti', 'Newest' ),
	'meno-recenti'         => sarafatto_theme_label( 'Meno recenti', 'Oldest' ),
	'prezzo-crescente'     => sarafatto_theme_label( 'Prezzo crescente', 'Price: low to high' ),
	'prezzo-decrescente'   => sarafatto_theme_label( 'Prezzo decrescente', 'Price: high to low' ),
);
if ( ! isset( $sort_labels[ $sort ] ) ) {
	$sort = 'recenti';
}
$english = function_exists( 'sarafatto_get_current_language' ) && 0 === strpos( sarafatto_get_current_language(), 'en' );
?>
<main id="main-content" class="site-main product-archive" tabindex="-1">
	<div class="container">
		<header class="product-archive__intro">
			<nav class="product-archive__breadcrumb" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Percorso di navigazione', 'Breadcrumb' ) ); ?>">
				<a href="<?php echo esc_url( function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Home', 'Home' ) ); ?></a>
				<span aria-hidden="true">›</span>
				<span aria-current="page"><?php echo esc_html( sarafatto_theme_label( 'Prodotti', 'Products' ) ); ?></span>
			</nav>
			<h1 class="product-archive__title"><span class="editorial-underline editorial-underline--02"><?php echo esc_html( sarafatto_theme_label( 'Prodotti', 'Products' ) ); ?></span></h1>
			<p class="product-archive__description"><?php echo esc_html( $english ? 'Objects that speak about you, your home and the lovely things of everyday life. Accessories, gift ideas and original creations, carefully selected for those who love the details that make a difference.' : 'Una collezione di oggetti che parlano di te, della tua casa e delle cose belle di ogni giorno. Accessori, idee regalo e creazioni originali, selezionate con cura per chi ama i dettagli che fanno la differenza.' ); ?></p>
		</header>

		<div class="product-archive__layout">
			<?php $filter_args = array( 'archive_url' => $archive_url, 'categories' => $categories, 'gift_ideas' => $gift_ideas, 'selected_cat' => $selected_cat, 'selected_gift' => $selected_gift, 'personalizable' => $personalizable, 'all_filters_active' => $all_filters_active, 'sort' => $sort ); ?>
			<aside class="product-filters product-filters--desktop" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Filtri prodotti', 'Product filters' ) ); ?>">
				<?php get_template_part( 'template-parts/products/archive-filters', null, $filter_args ); ?>
			</aside>
			<details class="product-filters product-filters--mobile">
				<summary class="product-filters__toggle"><span><?php echo esc_html( sarafatto_theme_label( 'Filtri', 'Filters' ) ); ?></span><span aria-hidden="true">+</span></summary>
				<?php get_template_part( 'template-parts/products/archive-filters', null, $filter_args ); ?>
			</details>

			<section class="product-archive__results" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Catalogo prodotti', 'Product catalog' ) ); ?>">
				<div class="product-archive__toolbar">
								<p class="product-archive__count"><?php printf( esc_html( 1 === (int) $wp_query->found_posts ? sarafatto_theme_label( '%s prodotto', '%s product' ) : sarafatto_theme_label( '%s prodotti', '%s products' ) ), esc_html( number_format_i18n( (int) $wp_query->found_posts ) ) ); ?></p>
					<form class="product-sort" method="get" action="<?php echo esc_url( $archive_url ); ?>">
						<?php if ( $selected_cat instanceof WP_Term ) : ?><input type="hidden" name="categoria" value="<?php echo esc_attr( $selected_cat->slug ); ?>"><?php endif; ?>
						<?php if ( $selected_gift instanceof WP_Term ) : ?><input type="hidden" name="idea" value="<?php echo esc_attr( $selected_gift->slug ); ?>"><?php endif; ?>
						<?php if ( $personalizable ) : ?><input type="hidden" name="personalizzabili" value="1"><?php endif; ?>
						<label for="product-sort-select"><?php echo esc_html( sarafatto_theme_label( 'Ordina per', 'Sort by' ) ); ?></label>
						<select id="product-sort-select" name="ordina">
							<?php foreach ( $sort_labels as $value => $label ) : ?><option value="<?php echo esc_attr( $value ); ?>" <?php selected( $sort, $value ); ?>><?php echo esc_html( $label ); ?></option><?php endforeach; ?>
						</select>
						<button class="product-sort__submit" type="submit"><?php echo esc_html( sarafatto_theme_label( 'Ordina', 'Sort' ) ); ?></button>
					</form>
				</div>

				<?php if ( have_posts() ) : ?>
					<ul class="product-grid">
						<?php while ( have_posts() ) : the_post(); $product_id = get_the_ID(); $flags = sarafatto_get_product_flags( $product_id ); $price = sarafatto_format_price( sarafatto_get_product_price( $product_id ) ); ?>
							<li class="product-card">
								<a class="product-card__link" href="<?php the_permalink(); ?>">
									<span class="product-card__media">
										<?php if ( has_post_thumbnail() ) : $thumbnail_id = get_post_thumbnail_id(); $image_alt = get_post_meta( $thumbnail_id, '_wp_attachment_image_alt', true ); if ( '' === trim( (string) $image_alt ) ) { $image_alt = get_the_title(); } ?>
											<?php echo wp_get_attachment_image( $thumbnail_id, 'large', false, array( 'class' => 'product-card__image', 'alt' => $image_alt, 'loading' => 'lazy', 'decoding' => 'async' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated by wp_get_attachment_image(). ?>
										<?php else : ?><span class="product-card__placeholder" aria-hidden="true"></span><?php endif; ?>
										<?php if ( $flags['is_sold_out'] ) : ?><span class="product-card__badge product-card__badge--sold-out"><?php echo esc_html( sarafatto_theme_label( 'Esaurito', 'Sold out' ) ); ?></span><?php elseif ( $flags['is_new'] ) : ?><span class="product-card__badge"><?php echo esc_html( sarafatto_theme_label( 'Novità', 'New' ) ); ?></span><?php endif; ?>
									</span>
									<span class="product-card__details"><span class="product-card__name"><?php the_title(); ?><span class="product-card__arrow" aria-hidden="true">↗</span></span><?php if ( $price ) : ?><span class="product-card__price"><?php echo esc_html( $price ); ?></span><?php endif; ?></span>
								</a>
							</li>
						<?php endwhile; ?>
					</ul>
					<?php
					$pagination = paginate_links(
						array(
							'total'      => (int) $wp_query->max_num_pages,
							'current'    => max( 1, get_query_var( 'paged' ) ),
							'type'       => 'list',
							'prev_text'  => sarafatto_theme_label( '← Precedente', '← Previous' ),
							'next_text'  => sarafatto_theme_label( 'Successiva →', 'Next →' ),
							'add_args'   => array_filter( array(
								'categoria' => $selected_cat instanceof WP_Term ? $selected_cat->slug : '',
								'idea' => $selected_gift instanceof WP_Term ? $selected_gift->slug : '',
								'personalizzabili' => $personalizable ? '1' : '',
								'ordina' => 'recenti' !== $sort ? $sort : '',
							) ),
						)
					);
					if ( $pagination ) : ?><nav class="product-pagination" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Paginazione prodotti', 'Product pagination' ) ); ?>"><?php echo wp_kses_post( $pagination ); ?></nav><?php endif; ?>
				<?php else : ?>
					<p class="product-archive__empty"><?php echo esc_html( sarafatto_theme_label( 'Non ci sono prodotti che corrispondono ai filtri selezionati.', 'No products match the selected filters.' ) ); ?></p>
				<?php endif; ?>
			</section>
		</div>
	</div>

	<?php $banner_id = function_exists( 'sarafatto_get_product_archive_banner_id' ) ? sarafatto_get_product_archive_banner_id() : 0; if ( $banner_id ) : ?>
		<section class="product-archive-cta" aria-labelledby="product-archive-cta-title">
			<figure class="product-archive-cta__media"><?php echo wp_get_attachment_image( $banner_id, 'large', false, array( 'class' => 'product-archive-cta__image', 'alt' => sarafatto_theme_label( 'Una donna con un post-it giallo davanti all’occhio', 'A woman with a yellow note covering one eye' ), 'loading' => 'lazy', 'decoding' => 'async' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated by wp_get_attachment_image(). ?></figure>
			<div class="product-archive-cta__content">
				<h2 id="product-archive-cta-title"><?php echo esc_html( sarafatto_theme_label( 'Scrivimi, posso aiutarti.', 'Message me, I can help.' ) ); ?></h2>
				<p><?php echo esc_html( $english ? 'Are you looking for something in particular or would you like to create something special, made just for you? Tell me your idea!' : 'Cerchi un oggetto in particolare o vuoi realizzare qualcosa di speciale, anche su misura? Raccontami la tua idea!' ); ?></p>
				<?php
				$archive_whatsapp = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url( $english ? 'Hi Sara, I saw the Products page and would like to ask you something.' : 'Ciao Sara, ho visto la pagina Prodotti e vorrei chiederti una cosa.' ) : '';
				if ( $archive_whatsapp ) {
					get_template_part( 'template-parts/components/button', null, array( 'label' => sarafatto_theme_label( 'Scrivimi su WhatsApp', 'Message me on WhatsApp' ), 'href' => $archive_whatsapp, 'variant' => 'primary', 'size' => 'md', 'icon' => 'whatsapp', 'external' => true ) );
				}
				?>
			</div>
		</section>
	<?php endif; ?>
</main>
<?php get_footer(); ?>
