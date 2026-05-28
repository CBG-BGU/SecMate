import React, { useState, useEffect } from 'react';

function DataModalProf({ isOpenProf, onCloseProf, currentValues }) {
    const [valuesProf, setValuesProf] = useState(currentValues);

    // Effect to initialize or reset values when the modal opens or currentValues change
    useEffect(() => {
        if (isOpenProf) {
            setValuesProf(currentValues);
        }
    }, [isOpenProf, currentValues]); // Depends on isOpenProf and currentValues

    const handleChangeProf = (event) => {
        const { name, value } = event.target;
        setValuesProf(prevValuesProf => ({
            ...prevValuesProf,
            [name]: parseInt(value, 10)
        }));
    };

    const handleSave = () => {
        onCloseProf(valuesProf); // Pass current state up to parent
    };

    const handleCancel = () => {
        onCloseProf(null); // Indicate cancellation without changing parent state
    };

    if (!isOpenProf) return null;

    return (
        <div style={{
            position: 'fixed',
            top: '14.5%',
            left: '15%',
            backgroundColor: 'rgba(28, 30, 58, 1)', // Dark background
            color: '#E0E0E0', // Light gray text for better readability
            padding: '20px',
            borderRadius: '10px', // Rounded corners
            boxShadow: '0 4px 8px rgba(0, 0, 0, 0.3)', // Soft shadow for depth
            zIndex: 1000,
            fontSize: '14px', // Font size
            width: 'auto', // Ensures the modal does not stretch too wide
            maxWidth: '500px' // Limits the maximum width of the modal
        }}>
            <h2 style={{ fontSize: '24px', marginBottom: '20px' }}>Your Tech Level</h2>
            {Object.keys(valuesProf).map(key => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', margin: '10px 0' }}>
                    <label style={{ width: '140px', marginRight: '10px' }}>{key}: </label>
                    <input
                        type="number"
                        name={key}
                        value={valuesProf[key] || ''} // Ensure the value is never undefined
                        onChange={handleChangeProf}
                        style={{
                            flex: 1,
                            maxWidth: '200px', // Adjusted for proper input size
                            backgroundColor: '#1E2043',
                            color: '#E0E0E0',
                            border: '1px solid #2C2E5E',
                            padding: '8px 10px',
                            fontSize: '14px',
                            textAlign: 'center'
                        }}
                    />
                </div>
            ))}
            <button onClick={handleSave} style={{
                backgroundColor: '#242648',
                color: '#FFF',
                border: 'none',
                padding: '10px 20px',
                cursor: 'pointer',
                marginRight: '10px',
                fontSize: '14px'
            }}>Save</button>
            <button onClick={handleCancel} style={{
                backgroundColor: '#242648',
                color: '#FFF',
                border: 'none',
                padding: '10px 20px',
                cursor: 'pointer',
                fontSize: '14px'
            }}>Cancel</button>
        </div>
    );
}

export default DataModalProf;
