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
