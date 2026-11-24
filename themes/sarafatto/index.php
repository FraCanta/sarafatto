<?php
/** Fallback template. */
get_header();

if ( is_search() ) {
	$listing_title = sprintf( sarafatto_theme_label( 'Risultati per “%s”', 'Results for “%s”' ), get_search_query() );
} elseif ( is_404() ) {
	$listing_title = sarafatto_theme_label( 'Pagina non trovata', 'Page not found' );
} elseif ( is_home() ) {
	$listing_title = sarafatto_theme_label( 'Novità', 'News' );
} elseif ( is_archive() ) {
	$listing_title = wp_strip_all_tags( get_the_archive_title() );
} elseif ( is_singular() ) {
	$listing_title = get_the_title();
} else {
	$listing_title = sarafatto_theme_label( 'Aggiornamenti', 'Updates' );
}
?>
<main id="main-content" class="site-main site-main--standard-page" tabindex="-1">
	<?php
	get_template_part(
		'template-parts/components/page-hero',
		null,
		array(
			'title' => $listing_title,
			'breadcrumbs' => array(
				array( 'label' => sarafatto_theme_label( 'Home', 'Home' ), 'url' => function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ),
				array( 'label' => $listing_title ),
			),
		)
	);
	?>
	<div class="container">
	<?php if ( have_posts() ) : while ( have_posts() ) : the_post(); $is_product = 'sarafatto_prodotto' === get_post_type(); $product_flags = $is_product && function_exists( 'sarafatto_get_product_flags' ) ? sarafatto_get_product_flags( get_the_ID() ) : array( 'is_sold_out' => false ); ?>
		<article <?php post_class(); ?>>
			<h2><a href="<?php the_permalink(); ?>"><?php the_title(); ?></a></h2>
			<?php if ( has_post_thumbnail() ) : ?>
				<figure<?php echo $is_product ? ' class="product-single__media"' : ''; ?>>
					<?php if ( $is_product && $product_flags['is_sold_out'] ) : ?><span class="product-single__badge"><?php echo esc_html( sarafatto_theme_label( 'Esaurito', 'Sold out' ) ); ?></span><?php endif; ?>
					<?php the_post_thumbnail( 'large' ); ?>
				</figure>
			<?php endif; ?>
			<?php the_excerpt(); ?>
			<?php if ( $is_product ) :
				$product_id = get_the_ID();
				if ( $product_flags['is_sold_out'] ) {
					$english = function_exists( 'sarafatto_get_current_language' ) && 0 === strpos( sarafatto_get_current_language(), 'en' );
					$message = $english
						? sprintf( 'Hi Sara, this product is currently sold out. I would like to know if it will be available again: %s %s', get_the_title(), get_permalink() )
						: sprintf( 'Ciao Sara, questo prodotto risulta esaurito. Vorrei sapere se tornerà disponibile: %s %s', get_the_title(), get_permalink() );
					$product_whatsapp = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url( $message ) : '';
					$product_cta_label = sarafatto_theme_label( 'Chiedi se tornerà disponibile', 'Ask if it will be available again' );
				} else {
					$product_whatsapp = function_exists( 'sarafatto_get_product_whatsapp_url' ) ? sarafatto_get_product_whatsapp_url( $product_id ) : '';
					$product_cta_label = sarafatto_theme_label( 'Chiedi disponibilità su WhatsApp', 'Ask about availability on WhatsApp' );
				}
				if ( $product_whatsapp ) : ?>
					<div class="product-single__actions">
						<?php get_template_part( 'template-parts/components/button', null, array( 'label' => $product_cta_label, 'href' => $product_whatsapp, 'variant' => 'primary', 'size' => 'md', 'icon' => 'whatsapp', 'external' => true ) ); ?>
					</div>
				<?php endif; ?>
			<?php endif; ?>
		</article>
	<?php endwhile; else : ?><p><?php esc_html_e( 'Non ci sono contenuti da mostrare.', 'sarafatto' ); ?></p><?php endif; ?>
	</div>
</main>
<?php get_footer();
