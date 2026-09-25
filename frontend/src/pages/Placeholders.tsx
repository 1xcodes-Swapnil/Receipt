function Placeholder({ name }: { name: string }) {
  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">{name}</h1>
      <div className="card mt-6 border-dashed text-center py-16">
        <p className="text-muted text-sm">
          <strong className="text-gray-600">Phase 1 foundation placeholder.</strong>
        </p>
        <p className="text-muted text-sm mt-1">
          This feature will be implemented in a later phase.
        </p>
      </div>
    </div>
  );
}

export function BugImmunity() {
  return <Placeholder name="Bug Immunity" />;
}

export function Replay() {
  return <Placeholder name="Replay" />;
}

export function AuditTrail() {
  return <Placeholder name="Audit Trail" />;
}
