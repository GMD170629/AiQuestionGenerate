"use client"

import * as React from "react"
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  AccordionProps,
} from '@mui/material'
import { ExpandMore } from '@mui/icons-material'
import { cn } from "@/lib/utils"

export interface CollapsibleProps {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  trigger?: React.ReactNode
  children?: React.ReactNode
  className?: string
  [key: string]: any
}

const Collapsible = React.forwardRef<HTMLDivElement, CollapsibleProps>(
  ({ open, onOpenChange, trigger, children, className, ...props }, ref) => {
    const [expanded, setExpanded] = React.useState(open ?? false)

    React.useEffect(() => {
      if (open !== undefined) {
        setExpanded(open)
      }
    }, [open])

    const handleChange = (_event: React.SyntheticEvent, isExpanded: boolean) => {
      setExpanded(isExpanded)
      onOpenChange?.(isExpanded)
    }

    return (
      <Accordion
        ref={ref}
        expanded={expanded}
        onChange={handleChange}
        className={cn(className)}
        {...props}
      >
        {trigger && (
          <AccordionSummary expandIcon={<ExpandMore />}>
            {trigger}
          </AccordionSummary>
        )}
        <AccordionDetails>
          {children}
        </AccordionDetails>
      </Accordion>
    )
  }
)
Collapsible.displayName = "Collapsible"

const CollapsibleTrigger = ({ children, ...props }: any) => {
  return <>{children}</>
}
CollapsibleTrigger.displayName = "CollapsibleTrigger"

const CollapsibleContent = ({ children, ...props }: any) => {
  return <>{children}</>
}
CollapsibleContent.displayName = "CollapsibleContent"

export { Collapsible, CollapsibleTrigger, CollapsibleContent }
