import React from "react";
import { Button } from "@/components/ui/button";

const HomePage = () => {
  return (
    <div className="min-h-screen p-12 bg-white flex flex-col items-center justify-center gap-8">
      <div className="text-center space-y-4 max-w-2xl">
        <h1 className="text-5xl font-display font-bold text-sr-text-blue tracking-tight">
          MindHire
        </h1>
        <p className="text-xl text-sr-gray">
          The global theme colors, typography, and button components have been configured.
        </p>
      </div>

      <div className="flex gap-6 mt-8">
        <Button>Request a Demo</Button>
        <Button variant="outline">Learn More</Button>
      </div>
    </div>
  );
};

export default HomePage;
