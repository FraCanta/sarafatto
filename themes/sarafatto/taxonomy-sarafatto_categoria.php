<?php
/** Dynamic product category catalog. */
get_header();

$term = get_queried_object();
if ( ! $term instanceof WP_Term || 'sarafatto_categoria' !== $term->taxonomy ) {
	get_footer();
	return;
}

$archive_url = function_exists( 'sarafatto_get_products_archive_url' ) ? sarafatto_get_products_archive_url() : get_post_type_archive_link( 'sarafatto_prodotto' );
$category_url = get_term_link( $term );
if ( is_wp_error( $category_url ) ) {
	$category_url = $archive_url;
}
$gift_ideas       = function_exists( 'sarafatto_get_product_archive_terms' ) ? sarafatto_get_product_archive_terms( 'sarafatto_idea_regalo' ) : array();
$occasions        = function_exists( 'sarafatto_get_product_archive_terms' ) ? sarafatto_get_product_archive_terms( 'sarafatto_occasione' ) : array();
$selected_gift    = function_exists( 'sarafatto_get_archive_filter_term' ) ? sarafatto_get_archive_filter_term( 'idea', 'sarafatto_idea_regalo' ) : null;
$selected_occasion = function_exists( 'sarafatto_get_archive_filter_term' ) ? sarafatto_get_archive_filter_term( 'occasione', 'sarafatto_occasione' ) : null;
$personalizable   = isset( $_GET['personalizzabili'] ) && is_scalar( $_GET['personalizzabili'] ) && '1' === sanitize_text_field( wp_unslash( $_GET['personalizzabili'] ) ); // phpcs:ignore WordPress.Security.NonceVerification.Recommended
$sort             = function_exists( 'sarafatto_get_product_archive_sort' ) ? sarafatto_get_product_archive_sort() : 'recenti';
$description      = term_description( $term->term_id, $term->taxonomy );
$description      = is_string( $description ) ? trim( wp_kses_post( $description ) ) : '';
global $wp_query;

$filter_args = array(
	'archive_url'        => $category_url,
	'all_products_url'   => $archive_url,
	'gift_ideas'         => $gift_ideas,
	'occasions'          => $occasions,
	'selected_cat'       => $term,
	'selected_gift'      => $selected_gift,
	'selected_occasion'  => $selected_occasion,
	'personalizable'     => $personalizable,
	'all_filters_active' => true,
	'sort'               => $sort,
	'category_context'   => true,
);
?>
<main id="main-content" class="site-main product-archive product-category-archive" tabindex="-1">
	<div class="container">
		<header class="product-archive__intro">
			<nav class="product-archive__breadcrumb" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Percorso di navigazione', 'Breadcrumb' ) ); ?>">
				<a href="<?php echo esc_url( function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Home', 'Home' ) ); ?></a>
				<span aria-hidden="true">›</span>
				<a href="<?php echo esc_url( $archive_url ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Prodotti', 'Products' ) ); ?></a>
				<span aria-hidden="true">›</span>
				<span aria-current="page"><?php echo esc_html( $term->name ); ?></span>
			</nav>
			<h1 class="product-archive__title"><span class="editorial-underline editorial-underline--02"><?php echo esc_html( $term->name ); ?></span></h1>
			<?php if ( '' !== $description ) : ?>
				<div class="product-archive__description"><?php echo $description; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Sanitized with wp_kses_post(). ?></div>
			<?php endif; ?>
		</header>

		<section class="product-category-archive__results" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Catalogo prodotti', 'Product catalog' ) ); ?>">
			<?php get_template_part( 'template-parts/products/archive-toolbar', null, array( 'action_url' => $category_url, 'selected_gift' => $selected_gift, 'selected_occasion' => $selected_occasion, 'personalizable' => $personalizable, 'category_context' => true, 'filters' => $filter_args ) ); ?>

			<?php if ( have_posts() ) : ?>
				<ul class="product-grid">
					<?php while ( have_posts() ) : the_post(); ?>
						<?php get_template_part( 'template-parts/products/product-card' ); ?>
					<?php endwhile; ?>
				</ul>
				<?php get_template_part( 'template-parts/products/archive-pagination', null, array( 'query' => $wp_query, 'selected_gift' => $selected_gift, 'selected_occasion' => $selected_occasion, 'personalizable' => $personalizable, 'sort' => $sort ) ); ?>
			<?php else : ?>
				<div class="product-archive__empty">
					<h2><?php echo esc_html( sarafatto_theme_label( 'Qui per ora niente.', 'Nothing here for now.' ) ); ?></h2>
					<p><?php echo esc_html( sarafatto_theme_label( 'Prova a cambiare qualche filtro o torna a vedere tutti i prodotti.', 'Try changing a filter or go back to browse all products.' ) ); ?></p>
					<?php get_template_part( 'template-parts/components/button', null, array( 'label' => sarafatto_theme_label( 'Vedi tutti i prodotti', 'See all products' ), 'href' => $archive_url, 'variant' => 'secondary', 'size' => 'md', 'trailing_icon' => 'arrow-right' ) ); ?>
				</div>
			<?php endif; ?>
		</section>
	</div>

	<?php get_template_part( 'template-parts/products/archive-cta', null, array( 'context' => $term->name ) ); ?>
</main>
<?php get_footer(); ?>
