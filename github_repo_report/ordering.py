"""Stable presentation order, shared by terminal, Markdown and JSON reports."""
COMPACT_FIELDS = (
    'repository', 'owner', 'age', 'languages', 'stars', 'forks',
    'repository_contents_size', 'homepage', 'links', 'topics',
    'license_detected_by_github', 'default_branch_head',
    'commits_reachable_from_default_branch_head',
    'issues_open', 'issues_closed', 'issues_total',
    'pr_open', 'pr_closed_unmerged', 'pr_closed_including_merged', 'pr_merged', 'pr_total',
    'tag_count', 'release_count_visible_to_caller',
)
DETAIL_FIELDS = ('collection', 'branches', 'contributors', 'readme_first_20_lines', 'supported_platforms')


def ordered_report(report):
    # Unknown future fields remain visible, ahead of the expansive detail blocks.
    keys = (*COMPACT_FIELDS, *(key for key in report if key not in COMPACT_FIELDS and key not in DETAIL_FIELDS), *DETAIL_FIELDS)
    return {key: report[key] for key in keys if key in report}
