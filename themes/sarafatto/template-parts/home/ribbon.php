<?php
/** Scroll-linked brand ribbon separator for the homepage. */
if ( ! defined( 'ABSPATH' ) ) { exit; }

$ribbon_text = implode( ' ', array_fill( 0, 12, 'SARÀ FATTO ·' ) );
?>
<div class="home-scroll-ribbon" aria-hidden="true">
	<svg class="home-scroll-ribbon__art" viewBox="0 0 1600 300" preserveAspectRatio="none" focusable="false">
		<defs>
			<path id="home-scroll-ribbon-path" d="M -40 50 C 110 70 75 190 270 215 C 405 245 530 155 735 150 C 890 145 980 225 1060 240 C 1170 265 1300 250 1390 240 C 1510 225 1565 188 1640 155" />
			<mask id="home-scroll-ribbon-reveal" maskUnits="userSpaceOnUse" x="0" y="0" width="1600" height="300">
				<rect x="0" y="0" width="1600" height="300" fill="black" />
				<path data-ribbon-reveal-path d="M -40 50 C 110 70 75 190 270 215 C 405 245 530 155 735 150 C 890 145 980 225 1060 240 C 1170 265 1300 250 1390 240 C 1510 225 1565 188 1640 155" fill="none" stroke="white" stroke-width="92" stroke-linecap="round" />
			</mask>
		</defs>
		<g data-ribbon-elastic mask="url(#home-scroll-ribbon-reveal)">
			<use href="#home-scroll-ribbon-path" class="home-scroll-ribbon__band" fill="none" stroke="#11b9d0" stroke-width="68" stroke-linecap="round" />
			<text class="home-scroll-ribbon__text">
				<textPath href="#home-scroll-ribbon-path" data-ribbon-marquee startOffset="0"><?php echo esc_html( $ribbon_text ); ?></textPath>
			</text>
		</g>
	</svg>
</div>
