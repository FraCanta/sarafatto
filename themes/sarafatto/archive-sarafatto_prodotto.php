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
$sort = function_exists( 'sarafatto_get_product_archive_sort' ) ? sarafatto_get_product_archive_sort() : 'recenti';
$products_label = sarafatto_theme_label( 'PRODOTTI', 'PRODUCTS' );
$catalog_title_before = sarafatto_theme_label( 'Tutti i ', 'All ' );
$catalog_title_accent = sarafatto_theme_label( 'prodotti', 'products' );
$catalog_title_after = sarafatto_theme_label( 'in un unico posto.', 'in one place.' );
?>
<main id="main-content" class="site-main product-archive product-archive--products" tabindex="-1">
	<section class="product-archive-hero" data-product-archive-hero aria-labelledby="product-archive-hero-title">
		<svg class="product-archive-hero__shape" viewBox="0 0 1440 820" preserveAspectRatio="none" aria-hidden="true" focusable="false">
			<path data-product-archive-curve d="M0 0H1440V680 C1080 840 360 840 0 680Z" />
		</svg>
		<div class="product-archive-hero__content">
			<h1 class="product-archive-hero__title" id="product-archive-hero-title">
				<span class="product-archive-hero__track" aria-hidden="true">
					<?php for ( $copy = 0; $copy < 2; $copy++ ) : ?>
						<span class="product-archive-hero__group">
							<?php for ( $item = 0; $item < 4; $item++ ) : ?>
								<span><?php echo esc_html( $products_label ); ?></span><span class="product-archive-hero__asterisk" aria-hidden="true">*</span>
							<?php endfor; ?>
						</span>
					<?php endfor; ?>
				</span>
				<span class="screen-reader-text"><?php echo esc_html( sarafatto_theme_label( 'Prodotti', 'Products' ) ); ?></span>
			</h1>
			<nav class="product-archive-hero__breadcrumb" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Percorso di navigazione', 'Breadcrumb' ) ); ?>">
				<a href="<?php echo esc_url( function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Home', 'Home' ) ); ?></a>
				<span aria-hidden="true">›</span>
				<span aria-current="page"><?php echo esc_html( sarafatto_theme_label( 'Prodotti', 'Products' ) ); ?></span>
			</nav>
		</div>
	</section>
	<section class="product-archive-intro" data-product-archive-intro aria-labelledby="product-archive-intro-title">
		<div class="product-archive-intro__inner container">
			<h2 class="product-archive-intro__title" id="product-archive-intro-title">
				<?php echo esc_html( $catalog_title_before ); ?><span class="product-archive-intro__accent"><?php echo esc_html( $catalog_title_accent ); ?><svg viewBox="0 0 220 20" aria-hidden="true" focusable="false"><path d="M5 14 C52 7 103 18 158 10 S203 8 216 11" /></svg></span><br><?php echo esc_html( $catalog_title_after ); ?>
			</h2>
			<?php if ( $categories ) : ?>
				<nav class="product-archive-intro__categories" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Categorie prodotto', 'Product categories' ) ); ?>">
					<ul>
						<?php foreach ( $categories as $category ) : ?>
							<?php $category_url = get_term_link( $category ); ?>
							<?php if ( is_wp_error( $category_url ) ) { continue; } ?>
							<li><a href="<?php echo esc_url( $category_url ); ?>"><?php echo esc_html( $category->name ); ?></a></li>
						<?php endforeach; ?>
					</ul>
				</nav>
			<?php endif; ?>
		</div>
	</section>
	<div class="container">
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
				<?php get_template_part( 'template-parts/products/archive-toolbar', null, array( 'action_url' => $archive_url, 'selected_cat' => $selected_cat, 'selected_gift' => $selected_gift, 'personalizable' => $personalizable ) ); ?>

				<?php if ( have_posts() ) : ?>
					<ul class="product-grid">
						<?php while ( have_posts() ) : the_post(); ?>
							<?php get_template_part( 'template-parts/products/product-card' ); ?>
						<?php endwhile; ?>
					</ul>
					<?php get_template_part( 'template-parts/products/archive-pagination', null, array( 'query' => $wp_query, 'selected_cat' => $selected_cat, 'selected_gift' => $selected_gift, 'personalizable' => $personalizable, 'sort' => $sort ) ); ?>
				<?php else : ?>
					<p class="product-archive__empty"><?php echo esc_html( sarafatto_theme_label( 'Non ci sono prodotti che corrispondono ai filtri selezionati.', 'No products match the selected filters.' ) ); ?></p>
				<?php endif; ?>
			</section>
		</div>
	</div>

	<?php get_template_part( 'template-parts/products/archive-cta' ); ?>
</main>
<?php get_footer(); ?>
