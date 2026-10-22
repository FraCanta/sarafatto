<?php
/** Home editorial service section for customisable products. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$content = function_exists( 'sarafatto_get_home_personalized_content' )
	? sarafatto_get_home_personalized_content()
	: array();
$title    = isset( $content['title'] ) && is_string( $content['title'] ) ? trim( $content['title'] ) : '';
$title_lines = preg_split( '/\R/u', $title );
$title_lines = is_array( $title_lines ) ? array_values( array_filter( array_map( 'trim', $title_lines ), 'strlen' ) ) : array();

// Keep the intended two-line title even when the saved setting has no line break.
if ( 1 === count( $title_lines ) && preg_match( '/^(Hai qualcosa)\s+(da dire\?|to say\?)$/iu', $title_lines[0], $title_match ) ) {
	$title_lines = array( $title_match[1], $title_match[2] );
}
$page     = isset( $content['page'] ) ? $content['page'] : null;

if ( '' === $title ) {
	return;
}

$alt = sarafatto_theme_label( 'T-shirt bianca con il ricamo “Pensati ventenne”', 'White T-shirt embroidered with “Pensati ventenne”' );
$section_id = 'home-personalized-title';
?>
<section class="home-personalized" aria-labelledby="<?php echo esc_attr( $section_id ); ?>">
	<div class="home-personalized__inner">
		<header class="home-personalized__content">
			<h2 class="home-personalized__title home-section-title<?php echo count( $title_lines ) > 1 ? ' home-personalized__title--multiline' : ''; ?>" id="<?php echo esc_attr( $section_id ); ?>">
				<?php foreach ( $title_lines as $title_line ) : ?>
					<span><?php echo esc_html( $title_line ); ?></span>
				<?php endforeach; ?>
			</h2>
			<p class="home-personalized__lead"><?php echo nl2br( esc_html( $content['lead'] ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Newlines are converted to safe br tags after escaping. ?></p>
		</header>
		<div class="home-personalized__stage">
			<svg class="home-personalized__ribbon" viewBox="0 0 1536 864" preserveAspectRatio="none" aria-hidden="true" focusable="false">
				<g class="home-personalized__ribbon-track" data-personalized-ribbon-track>
					<path class="home-personalized__ribbon-band" data-personalized-ribbon-path d="M-140 430 C35 306 164 248 310 315 C457 383 570 511 720 385 C856 271 958 181 1090 276 C1242 385 1410 485 1680 250" />
				</g>
			</svg>
			<img class="home-personalized__image" src="<?php echo esc_url( get_theme_file_uri( 'assets/images/home-personalized-shirt.png' ) ); ?>" alt="<?php echo esc_attr( $alt ); ?>" width="1448" height="1086" loading="lazy" decoding="async" />
			<p class="home-personalized__body"><?php echo nl2br( esc_html( $content['body'] ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Newlines are converted to safe br tags after escaping. ?></p>
		</div>
		<?php if ( $page instanceof WP_Post ) : ?>
			<div class="home-personalized__footer">
				<?php
				get_template_part(
					'template-parts/components/button',
					null,
					array(
						'label'         => $content['cta'],
						'href'          => get_permalink( $page->ID ),
						'variant'       => 'primary',
						'size'          => 'lg',
						'trailing_icon' => 'arrow-right',
						'class'         => 'home-personalized__button',
					)
				);
				?>
			</div>
		<?php endif; ?>
	</div>
</section>
