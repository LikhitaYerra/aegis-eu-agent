import { ExternalLink, FileCheck2, MapPin } from 'lucide-react'
import type { AssessmentSource } from '../api'

type SourceListProps = {
  sources: AssessmentSource[]
}

export function SourceList({ sources }: SourceListProps) {
  return (
    <div className="source-list">
      {sources.map((source, index) => (
        <article className="source-card" key={`${source.source}-${index}`}>
          <div className="source-index">S{index + 1}</div>
          <div className="source-body">
            <div className="source-heading">
              <div>
                <span className="source-type">
                  <FileCheck2 size={14} aria-hidden="true" />
                  Official evidence
                </span>
                <h4>{source.title}</h4>
              </div>
              <span className="jurisdiction">
                <MapPin size={13} aria-hidden="true" />
                {source.jurisdiction}
              </span>
            </div>
            <p>{source.excerpt}</p>
            <div className="source-footer">
              <span>Relevance {source.score.toFixed(2)}</span>
              <a href={source.source} target="_blank" rel="noreferrer">
                Open source
                <ExternalLink size={14} aria-hidden="true" />
              </a>
            </div>
          </div>
        </article>
      ))}
    </div>
  )
}
