import Autocomplete from '@mui/material/Autocomplete'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

export interface RecipientOption {
  id: string
  name: string
}

interface RecipientPickerProps {
  options: RecipientOption[]
  selectedIds: string[]
  onChange: (ids: string[]) => void
  label?: string
}

// First version of EXPERIENCE.md's shared "Recipient picker" component —
// a plain multi-select of individual, active, WhatsApp-addressable Users
// only. `options` must already exclude inactive and unaddressable
// (mobile === null) Users; this component does no filtering of its own.
// Epic 4's Notifications > Compose extends this (or builds its own) once
// it needs to resolve a mixed User/Team/RecipientList selection with a
// de-duplicated count — that cross-type dedupe logic is explicitly not
// this component's job yet.
function RecipientPicker({ options, selectedIds, onChange, label = 'Members' }: RecipientPickerProps) {
  const selectedOptions = options.filter((option) => selectedIds.includes(option.id))

  return (
    <div>
      <Autocomplete
        multiple
        options={options}
        value={selectedOptions}
        getOptionLabel={(option) => option.name}
        isOptionEqualToValue={(option, value) => option.id === value.id}
        onChange={(_, value) => onChange(value.map((option) => option.id))}
        renderInput={(params) => <TextField {...params} label={label} />}
      />
      <Typography variant="caption" color="text.secondary">
        {selectedIds.length} selected
      </Typography>
    </div>
  )
}

export default RecipientPicker
