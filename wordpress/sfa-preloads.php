<?php
/**
 * Sharp Football Analysis: server-side preload tables.
 *
 * Renders each tool's crawlable stat table into the page HTML so search engines
 * and no-JavaScript visitors see real data. The interactive tool hides it once
 * it has painted; if the tool's data fetch fails, the table stays visible.
 *
 *   [sharp_football_personnel]   personnel grouping frequency
 *   [sharp_football_pace]        offensive pace
 *   [sharp_football_matchup]     weekly matchups, whole slate; game="KC-BUF" keeps one game
 *   [sharp_football_boxscore]    box scores, latest played week; game="CLE-JAX" keeps one game
 *   [sharp_football_proe]        pass rate over expected, offense and defense, latest season
 *   [sharp_football_redzone]     red zone targets and carries by player, latest season
 *   [sharp_football_redzone_team] red zone offense and defense efficiency, latest season
 *   [sharp_football_firsttd_team]   first touchdown rate by team, current season
 *   [sharp_football_firsttd_player] first touchdown scorers, current season
 *
 * Paste this file into Code Snippets as a PHP (Functions) snippet, scope "Run
 * everywhere", omitting the opening PHP tag on line 1. Code Snippets supplies it.
 *
 * Structure note: no top-level `return`, no `define()`, no closures. Code
 * Snippets evaluates snippet bodies, and all three behave differently there
 * than in a normal include. This mirrors the shape of the injury report
 * snippet, which has been running in production.
 */

/**
 * All configuration lives here. A function rather than constants so the snippet
 * body is safe to evaluate more than once.
 */
function sfa_preload_config() {
	return array(
		'url'       => 'https://rmsummerlin.github.io/SFAStatsPages/data/preloads.json',
		'timezone'  => 'America/New_York',
		'day'       => 'tuesday',
		'time'      => '23:00',
		'retry'     => 2 * MINUTE_IN_SECONDS,
		'lock_ttl'  => 30,
		'option'    => 'sfa_preloads_last_good',
		'lock'      => 'sfa_preloads_lock',
		'transient' => 'sfa_preloads_html',
	);
}

/**
 * Seconds until the next scheduled refresh. Anchored to a wall-clock moment
 * rather than a rolling week, so the cache turns over just after the week's
 * data lands instead of drifting with traffic.
 */
function sfa_preload_ttl() {
	$cfg = sfa_preload_config();
	try {
		$tz   = new DateTimeZone( $cfg['timezone'] );
		$now  = new DateTime( 'now', $tz );
		$next = new DateTime( $cfg['day'] . ' ' . $cfg['time'], $tz );
		if ( $now >= $next ) {
			$next->modify( '+7 days' );
		}
		return max( $next->getTimestamp() - $now->getTimestamp(), MINUTE_IN_SECONDS );
	} catch ( Exception $e ) {
		return WEEK_IN_SECONDS;
	}
}

/**
 * Table-only whitelist, deliberately narrower than wp_kses_post. The manifest is
 * ours and arrives over HTTPS, but it is still remote HTML echoed into live
 * articles, so nothing executable can reach the page even if it were tampered
 * with. Verified against the generated tables, so nothing is silently stripped.
 */
function sfa_preload_allowed_tags() {
	$cell = array(
		'scope'   => true,
		'colspan' => true,
		'rowspan' => true,
		'class'   => true,
	);
	return array(
		'table'   => array( 'class' => true ),
		'caption' => array( 'class' => true ),
		'thead'   => array(),
		'tbody'   => array(),
		'tfoot'   => array(),
		'tr'      => array( 'class' => true ),
		'th'      => $cell,
		'td'      => $cell,
		'span'    => array( 'class' => true ),
		'b'       => array(),
		'strong'  => array(),
		'em'      => array(),
		'i'       => array(),
		'abbr'    => array( 'title' => true ),
	);
}

/**
 * Fetch and sanitise the manifest. Returns tool => html, or null on any failure.
 * Sanitising happens once per fetch rather than per render; wp_kses is
 * regex-heavy and the result is identical every time.
 */
function sfa_preload_fetch() {
	$cfg  = sfa_preload_config();
	$resp = wp_remote_get(
		$cfg['url'],
		array(
			'timeout'    => 4,
			'user-agent' => 'SFAStatsPages preload/1.0',
			'headers'    => array( 'Accept' => 'application/json' ),
		)
	);

	$failed = '';
	if ( is_wp_error( $resp ) ) {
		$failed = 'wp_error: ' . $resp->get_error_message();
	} elseif ( 200 !== (int) wp_remote_retrieve_response_code( $resp ) ) {
		$failed = 'http ' . wp_remote_retrieve_response_code( $resp );
	}
	if ( $failed ) {
		error_log( 'sfa_preloads: fetch failed (' . $failed . ') for ' . $cfg['url'] );
		return null;
	}

	$decoded = json_decode( wp_remote_retrieve_body( $resp ), true );
	if ( ! is_array( $decoded ) || empty( $decoded ) ) {
		error_log( 'sfa_preloads: response was not a JSON object for ' . $cfg['url'] );
		return null;
	}

	$clean = array();
	foreach ( $decoded as $key => $html ) {
		if ( is_string( $key ) && is_string( $html ) && '' !== trim( $html ) ) {
			$clean[ sanitize_key( $key ) ] = wp_kses( $html, sfa_preload_allowed_tags() );
		}
	}
	if ( empty( $clean ) ) {
		error_log( 'sfa_preloads: nothing survived sanitising for ' . $cfg['url'] );
		return null;
	}
	return $clean;
}

/**
 * Cached manifest.
 *
 * A transient is the live cache; an option holds the last known good copy, so a
 * brief GitHub outage serves a stale table rather than an empty one. A short
 * lock stops every concurrent request refreshing at once when the cache expires.
 */
function sfa_preload_manifest() {
	static $memo = null;
	if ( null !== $memo ) {
		return $memo;  // one lookup per request, however many shortcodes run
	}

	$cfg    = sfa_preload_config();
	$forced = isset( $_GET['sfa_refresh'] ) && current_user_can( 'edit_posts' );

	if ( ! $forced ) {
		$cached = get_transient( $cfg['transient'] );
		if ( false !== $cached ) {
			$memo = is_array( $cached ) ? $cached : array();
			return $memo;
		}
		if ( false !== get_transient( $cfg['lock'] ) ) {
			$memo = (array) get_option( $cfg['option'], array() );
			return $memo;
		}
	}
	set_transient( $cfg['lock'], 1, $cfg['lock_ttl'] );

	$fresh = sfa_preload_fetch();
	delete_transient( $cfg['lock'] );

	if ( null === $fresh ) {
		$fallback = (array) get_option( $cfg['option'], array() );
		set_transient( $cfg['transient'], $fallback, $cfg['retry'] );
		$memo = $fallback;
		return $memo;
	}

	update_option( $cfg['option'], $fresh, false );  // no autoload
	set_transient( $cfg['transient'], $fresh, sfa_preload_ttl() );
	$memo = $fresh;
	return $memo;
}

/**
 * Styles for the preload table.
 *
 * The shortcode output sits outside .pt-root, so the tool fragment's own CSS
 * cannot reach it. Printed inline on first render rather than enqueued, so the
 * snippet stays self-contained and costs nothing on pages without a shortcode.
 * Every selector is scoped under .sfa-preload; nothing leaks into the theme.
 */
function sfa_preload_styles() {
	static $done = false;
	if ( $done ) {
		return '';
	}
	$done = true;
	/*
	 * Every property is declared on the table elements themselves rather than
	 * left to inherit, with !important and the full element path. Inheritance
	 * loses to any theme rule matching th or td directly, and Avada's do: on
	 * the live site its th rule painted the row headers dark on dark and the
	 * column headers in the red condensed heading face. The other tables are
	 * hidden by their tool before a reader sees them; the first touchdown
	 * tables are the article, so they have to win outright.
	 *
	 * Brand values from docs/avada-embed-rules.md: text #111, header band
	 * #f4f5f7, borders #dde2e8, stripe #f6f6f6, white cells. The font is the
	 * article's own, inherited from the page rather than from the theme's th.
	 *
	 * The caption stays in the markup for crawlers and screen readers but is
	 * clipped off screen: readers get the article copy instead. The first
	 * column stays put while a phone pans across the figures.
	 */
	return '<style>'
		. '.sfa-preload{margin:0 0 18px;overflow-x:auto;-webkit-overflow-scrolling:touch}'
		. '.sfa-preload table,.sfa-preload table thead,.sfa-preload table tbody,'
		. '.sfa-preload table tfoot,.sfa-preload table tr,.sfa-preload table th,'
		. '.sfa-preload table td,.sfa-preload table caption,.sfa-preload table abbr{'
		. 'font-family:inherit!important;font-size:14px!important;font-weight:400!important;'
		. 'font-style:normal!important;line-height:1.3!important;color:#111!important;'
		. 'background:#fff!important;border:0!important;text-align:left!important;'
		. 'text-transform:none!important;letter-spacing:normal!important;'
		. 'text-decoration:none!important;text-shadow:none!important;box-shadow:none!important;'
		. 'vertical-align:middle!important;margin:0!important;padding:0!important}'
		. '.sfa-preload table{border-collapse:collapse!important;width:100%!important}'
		. '.sfa-preload table caption{position:absolute!important;width:1px!important;height:1px!important;'
		. 'overflow:hidden!important;clip:rect(0 0 0 0)!important;clip-path:inset(50%)!important;'
		. 'white-space:nowrap!important}'
		. '.sfa-preload table th,.sfa-preload table td{border:1px solid #dde2e8!important;'
		. 'padding:7px 9px!important;text-align:center!important;white-space:nowrap!important}'
		. '.sfa-preload table thead tr th{background:#f4f5f7!important;font-weight:700!important;'
		. 'text-align:center!important;border-bottom:2px solid #111!important}'
		. '.sfa-preload table tbody tr th[scope=row]{text-align:left!important;font-weight:700!important}'
		. '.sfa-preload table tr th:first-child{position:sticky!important;left:0!important;z-index:1!important;'
		. 'box-shadow:1px 0 0 #dde2e8!important}'
		. '.sfa-preload table tbody tr:nth-child(even) th,.sfa-preload table tbody tr:nth-child(even) td{'
		. 'background:#f6f6f6!important}'
		. '</style>';
}

/**
 * Render one tool's table.
 *
 * data-sfa-preload is what the interactive tool looks for to hide this once it
 * has painted, wherever on the page it sits.
 */
function sfa_preload_render( $tool ) {
	$manifest = sfa_preload_manifest();
	$tool     = sanitize_key( $tool );

	if ( empty( $manifest[ $tool ] ) ) {
		// Never break the page. Leave a trace an editor can find in view-source.
		return '<!-- sfa preload: no table available for ' . esc_html( $tool ) . ' -->';
	}

	return sfa_preload_styles()
		. '<div class="sfa-preload" data-sfa-preload="' . esc_attr( $tool ) . '">'
		. $manifest[ $tool ]  // already sanitised at fetch time
		. '</div>';
}

/*
 * One shortcode per tool, so they read clearly in the CMS. They share the cache
 * above, so the count of shortcodes on a page does not affect request count.
 *
 * To add a tool: copy one of these pairs and match the key in data/preloads.json,
 * then add hideServerPreload() to that tool's render path.
 *
 * To force a refresh: load a page carrying a shortcode with ?sfa_refresh=1 while
 * logged in as an editor, or delete the sfa_preloads_last_good option.
 */
function sfa_preload_personnel_shortcode() {
	return sfa_preload_render( 'personnel_grouping' );
}
add_shortcode( 'sharp_football_personnel', 'sfa_preload_personnel_shortcode' );

function sfa_preload_pace_shortcode() {
	return sfa_preload_render( 'pace' );
}
add_shortcode( 'sharp_football_pace', 'sfa_preload_pace_shortcode' );

/*
 * The matchup table carries every game of the current week, two rows per game
 * (one per offense). A game preview article can keep just its own game with
 * [sharp_football_matchup game="KC-BUF"], away team first, matching the row
 * class the pull script writes (g-kc-buf). Unknown or absent game: whole slate.
 */
function sfa_preload_matchup_shortcode( $atts ) {
	$atts = shortcode_atts( array( 'game' => '' ), $atts, 'sharp_football_matchup' );
	return sfa_preload_keep_game( sfa_preload_render( 'matchup' ), $atts['game'] );
}
add_shortcode( 'sharp_football_matchup', 'sfa_preload_matchup_shortcode' );

/*
 * The box score table carries every game of the latest played week, two rows
 * per game (one per offense). A recap article keeps just its own game with
 * [sharp_football_boxscore game="CLE-JAX"], away team first, same row class
 * convention as the matchup table.
 */
function sfa_preload_boxscore_shortcode( $atts ) {
	$atts = shortcode_atts( array( 'game' => '' ), $atts, 'sharp_football_boxscore' );
	return sfa_preload_keep_game( sfa_preload_render( 'boxscore' ), $atts['game'] );
}
add_shortcode( 'sharp_football_boxscore', 'sfa_preload_boxscore_shortcode' );

function sfa_preload_proe_shortcode() {
	return sfa_preload_render( 'proe' );
}
add_shortcode( 'sharp_football_proe', 'sfa_preload_proe_shortcode' );

/*
 * Two red zone pages, one data pull. The player table carries the top 50 by
 * red zone opportunities and the inside-the-5 carries list; the team table
 * carries every offense and every defense.
 */
function sfa_preload_redzone_shortcode() {
	return sfa_preload_render( 'redzone' );
}
add_shortcode( 'sharp_football_redzone', 'sfa_preload_redzone_shortcode' );

function sfa_preload_redzone_team_shortcode() {
	return sfa_preload_render( 'redzone_team' );
}
add_shortcode( 'sharp_football_redzone_team', 'sfa_preload_redzone_team_shortcode' );

/*
 * The first and anytime touchdown article: two tables, one pull, no
 * interactive tool. Each shortcode goes in its own Text Block, so the article
 * carries both without needing two code blocks. Nothing hides them, so they
 * are the tables readers see, not just crawlers.
 */
function sfa_preload_firsttd_team_shortcode() {
	return sfa_preload_render( 'firsttd_team' );
}
add_shortcode( 'sharp_football_firsttd_team', 'sfa_preload_firsttd_team_shortcode' );

function sfa_preload_firsttd_player_shortcode() {
	return sfa_preload_render( 'firsttd_player' );
}
add_shortcode( 'sharp_football_firsttd_player', 'sfa_preload_firsttd_player_shortcode' );

/**
 * Keep only the rows of one game (row class g-<away>-<home>) in a table that
 * carries a whole week. Unknown or absent game: the whole table.
 */
function sfa_preload_keep_game( $html, $game ) {
	$game = strtolower( preg_replace( '/[^A-Za-z-]/', '', (string) $game ) );
	if ( '' === $game || false === strpos( $html, 'class="g-' . $game . '"' ) ) {
		return $html;
	}
	// Drop every body row that is not this game. The generated markup never
	// nests <tr>, so a non-greedy match is safe, and the negative lookahead
	// keeps this a plain preg_replace rather than a callback (no closures in a
	// Code Snippets body, per the structure note above).
	$kept = preg_replace(
		'#<tr class="g-(?!' . preg_quote( $game, '#' ) . '")[a-z-]+">.*?</tr>#s',
		'',
		$html
	);
	return null === $kept ? $html : $kept;
}
