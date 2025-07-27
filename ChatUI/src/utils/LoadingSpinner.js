import React from 'react';

const LoadingSpinner = () => {
  return (
    <div id="loader"   className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 " style={{zIndex: 1000}}>
      <div className="relative z-50">
        {/* <div className="spinner"></div>
        <img src="/mozaikloadingicon.png" alt="M" className="center-image absolute inset-0 m-auto"/> */}
      </div>
      {/* <div className="absolute inset-0 bg-black bg-opacity-10 backdrop-blur-xs"></div>/ */}
    </div>
  );
};

export default LoadingSpinner;
