import { useEffect, useState } from 'react'
import Autocomplete from '@mui/material/Autocomplete'
import Chip from '@mui/material/Chip'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { apiFetch } from '../api/authClient'

export interface RecipientEntry {
  id: string
  name: string
  type: 'user' | 'team' | 'recipient_list'
}

export interface ResolvedCounts {
  selectedCount: number
  uniqueCount: number
  overlapCount: number
  ineligibleCount: number
}

interface MixedRecipientPickerProps {
  options: RecipientEntry[]
  selected: RecipientEntry[]
  onChange: (selected: RecipientEntry[]) => void
  onResolvedChange: (resolved: ResolvedCounts | null) => void
}

const TYPE_GROUP_LABELS: Record<RecipientEntry['type'], string> = {
  user: 'Users',
  team: 'Teams',
  recipient_list: 'Groups & Channels',
}

function dedupeNote(resolved: ResolvedCounts): string {
  const parts: string[] = []
  if (resolved.overlapCount > 0) {
    parts.push(`${resolved.overlapCount} overlaps merged`)
  }
  if (resolved.ineligibleCount > 0) {
    parts.push(`${resolved.ineligibleCount} inactive or not opted in`)
  }
  const suffix = parts.length > 0 ? ` (${parts.join(', ')})` : ''
  return `${resolved.selectedCount} selected → ${resolved.uniqueCount} unique recipients${suffix}`
}

// The cross-type (User+Team+RecipientList) dedupe logic RecipientPicker.tsx
// explicitly defers — calls POST /notifications/resolve-recipients
// (debounced) on every selection change, using the same resolution
// function the send path uses (AD-2), so the live count here is never
// bigger than what actually gets sent.
function MixedRecipientPicker({
  options,
  selected,
  onChange,
  onResolvedChange,
}: MixedRecipientPickerProps) {
  const [resolved, setResolved] = useState<ResolvedCounts | null>(null)

  useEffect(() => {
    if (selected.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clears resolved counts synchronously when the picker becomes empty, mirroring this codebase's other "reset on empty" effects
      setResolved(null)
      onResolvedChange(null)
      return
    }

    let cancelled = false
    const timeoutId = setTimeout(async () => {
      try {
        const response = await apiFetch('/notifications/resolve-recipients', {
          method: 'POST',
          body: JSON.stringify({
            user_ids: selected.filter((entry) => entry.type === 'user').map((entry) => entry.id),
            team_ids: selected.filter((entry) => entry.type === 'team').map((entry) => entry.id),
            recipient_list_ids: selected
              .filter((entry) => entry.type === 'recipient_list')
              .map((entry) => entry.id),
          }),
        })
        if (cancelled || !response.ok) return
        const body = await response.json()
        const next: ResolvedCounts = {
          selectedCount: body.selected_count,
          uniqueCount: body.unique_count,
          overlapCount: body.overlap_count,
          ineligibleCount: body.ineligible_count,
        }
        setResolved(next)
        onResolvedChange(next)
      } catch {
        // Network failure — leave the previous resolved counts in place
        // rather than clearing them out from under the Administrator.
      }
    }, 300)

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onResolvedChange is expected to be referentially stable per call site convention in this codebase
  }, [selected])

  return (
    <div>
      <Autocomplete
        multiple
        options={options}
        value={selected}
        groupBy={(option) => TYPE_GROUP_LABELS[option.type]}
        getOptionLabel={(option) => option.name}
        isOptionEqualToValue={(option, value) => option.id === value.id && option.type === value.type}
        onChange={(_, value) => onChange(value)}
        renderValue={(value, getItemProps) =>
          value.map((option, index) => {
            const { key, ...itemProps } = getItemProps({ index })
            return <Chip key={key} label={option.name} {...itemProps} />
          })
        }
        renderInput={(params) => <TextField {...params} label="Recipients" />}
      />
      {resolved && (
        <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 1 }}>
          {dedupeNote(resolved)}
        </Typography>
      )}
    </div>
  )
}

export default MixedRecipientPicker
